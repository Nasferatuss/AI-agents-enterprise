"""Durable run store for long-lived agent/workflow runs (durability hardening).

Generic persistence for runs that must outlive the process that started them:

* the **human-in-the-loop workflow gate** — a run can sit `awaiting_approval` for
  hours, so its state must survive a gateway restart or it can never be resumed;
* the **async flagship run model** — submit returns `202 + run_id`, the work runs
  in the background, and the client polls; the run state has to be queryable from
  any replica, not just the one that accepted the request.

One row per run (`AgentRun`); the serialized domain object lives in `payload`.
`idempotency_key` dedupes expensive re-submissions (a client/LB retry must not
launch a second costly run). Best-effort like the trace store: callers keep an
in-memory authoritative copy and treat the DB as a durable mirror, so a DB outage
degrades to the old in-memory behavior instead of breaking the request.
"""

import datetime

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError

from workbench_observability.db import get_sessionmaker
from workbench_observability.models import AgentRun
from workbench_observability.schema import RunRecord
from workbench_shared.logging import get_logger

log = get_logger(__name__)

# In-flight statuses: a run that hasn't reached a terminal state yet. Used by the
# worker's startup reconciler to pick up runs orphaned by a crash. NOTE: distinct
# from schema.NON_TERMINAL_STATUSES (trace recording) — this one is the run-store
# reconcile set and includes "pending", which that one deliberately omits.
NON_TERMINAL_RUN_STATUSES = ("pending", "running")


# Run-store timestamps are compared/sorted as plain strings (the sweep's `<`, the
# list `ORDER BY`). For that to equal chronological order the format must be
# FIXED-WIDTH: `datetime.isoformat()` silently DROPS the fractional part when
# microseconds == 0 ("…:55+00:00" vs "…:55.000001+00:00"), and "+" < "." so a
# whole-second stamp would mis-sort within its second. Format explicitly instead —
# always 6-digit microseconds + a 'Z' — so every writer is byte-comparable. (We keep
# string columns rather than a timestamptz migration on purpose: agent_runs is a
# transient operational table, sqlite is the dev/test backend, and a fixed-width UTC
# string removes the fragility without a live-data schema change.)
_TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _fmt(dt: datetime.datetime) -> str:
    return dt.strftime(_TS_FORMAT)


def _utc_now() -> str:
    return _fmt(datetime.datetime.now(datetime.UTC))


def _to_record(row: AgentRun) -> RunRecord:
    return RunRecord(
        run_id=row.id,
        kind=row.kind,
        status=row.status,
        payload=row.payload or {},
        idempotency_key=row.idempotency_key,
        error=row.error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def upsert_run(
    *,
    run_id: str,
    kind: str,
    status: str,
    payload: dict,
    idempotency_key: str | None = None,
    error: str | None = None,
) -> RunRecord | None:
    """Insert or update a run row. Returns the stored record, or None on failure.

    Best-effort: a persistence error is logged and swallowed so the caller's
    in-memory path keeps working (durability is a mirror, not the critical path).
    """
    now = _utc_now()
    try:
        async with get_sessionmaker()() as session:
            row = await session.get(AgentRun, run_id)
            if row is None:
                row = AgentRun(id=run_id, kind=kind, created_at=now)
                session.add(row)
            row.status = status
            row.payload = payload
            row.error = error
            row.updated_at = now
            if idempotency_key is not None:
                row.idempotency_key = idempotency_key
            await session.commit()
            return _to_record(row)
    except Exception as exc:  # noqa: BLE001 — durability mirror must not break the request
        log.warning("run persistence failed", run_id=run_id, kind=kind, error=str(exc))
        return None


async def create_run(
    *,
    run_id: str,
    kind: str,
    status: str,
    payload: dict,
    idempotency_key: str | None = None,
) -> RunRecord:
    """Insert a NEW run, race-safe against the (kind, idempotency_key) UNIQUE.

    Returns the stored record. If another concurrent submit already created a run
    with the same idempotency key, the INSERT hits IntegrityError and we return
    the EXISTING run instead — so its ``run_id`` will differ from the one passed
    in, and the caller must not launch a second (duplicate) execution.
    """
    now = _utc_now()
    try:
        async with get_sessionmaker()() as session:
            row = AgentRun(
                id=run_id,
                kind=kind,
                status=status,
                payload=payload,
                idempotency_key=idempotency_key,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.commit()
            return _to_record(row)
    except IntegrityError:
        # Lost the idempotency race (or a run_id collision) — return the winner.
        if idempotency_key is not None:
            existing = await get_run_by_idempotency_key(kind, idempotency_key)
            if existing is not None:
                return existing
        existing = await get_run(run_id)
        if existing is not None:
            return existing
        raise
    except Exception as exc:  # noqa: BLE001 — best-effort: let the caller proceed
        log.warning("run create failed", run_id=run_id, kind=kind, error=str(exc))
        return RunRecord(
            run_id=run_id,
            kind=kind,
            status=status,
            payload=payload,
            idempotency_key=idempotency_key,
            error=None,
            created_at=now,
            updated_at=now,
        )


async def claim_run(*, run_id: str, lease_seconds: int) -> bool:
    """Atomically transition a run to ``running`` iff it is *claimable*, returning
    ``True`` only for the caller that won the claim.

    Claimable = the row is ``pending`` (never started) **or** ``running`` but with a
    heartbeat (``updated_at``) older than ``lease_seconds`` — i.e. its previous owner
    is presumed dead (a *lease*/visibility-timeout). This is a single compare-and-set
    ``UPDATE ... WHERE`` (not read-then-write), so when the same run is delivered to
    two workers concurrently the database serializes the row update and exactly one
    gets ``rowcount == 1``; the loser sees the row already ``running`` with a fresh
    heartbeat and returns ``False``. This closes the double-execution window the old
    read-then-check had — a run is only ever actively executed by one worker.

    A run whose owner genuinely crashed becomes claimable again once its lease
    expires, so it can be re-driven; the stuck-run sweeper is the terminal backstop.

    On a store error we log and return ``True`` (fail-open): durability is a mirror,
    so a DB outage degrades to the old in-memory behavior rather than dropping the run.
    """
    now = datetime.datetime.now(datetime.UTC)
    stale_cutoff = _fmt(now - datetime.timedelta(seconds=lease_seconds))
    try:
        async with get_sessionmaker()() as session:
            stmt = (
                update(AgentRun)
                .where(
                    AgentRun.id == run_id,
                    or_(
                        AgentRun.status == "pending",
                        and_(
                            AgentRun.status == "running",
                            AgentRun.updated_at < stale_cutoff,
                        ),
                    ),
                )
                .values(status="running", updated_at=_fmt(now))
            )
            result = await session.execute(stmt)
            await session.commit()
            return (result.rowcount or 0) == 1
    except Exception as exc:  # noqa: BLE001 — fail-open: mirror outage must not drop the run
        log.warning("run claim failed (proceeding fail-open)", run_id=run_id, error=str(exc))
        return True


async def get_run(run_id: str) -> RunRecord | None:
    """Load a run by id, or None if absent / on a store error."""
    try:
        async with get_sessionmaker()() as session:
            row = await session.get(AgentRun, run_id)
            return _to_record(row) if row else None
    except Exception as exc:  # noqa: BLE001
        log.warning("run load failed", run_id=run_id, error=str(exc))
        return None


async def get_run_by_idempotency_key(kind: str, idempotency_key: str) -> RunRecord | None:
    """Return an existing run for (kind, idempotency_key), or None. Powers dedup."""
    if not idempotency_key:
        return None
    try:
        async with get_sessionmaker()() as session:
            stmt = (
                select(AgentRun)
                .where(AgentRun.kind == kind, AgentRun.idempotency_key == idempotency_key)
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _to_record(row) if row else None
    except Exception as exc:  # noqa: BLE001
        log.warning("idempotency lookup failed", kind=kind, error=str(exc))
        return None


async def list_runs(kind: str | None = None, limit: int = 200) -> list[RunRecord]:
    """Most-recent-first runs, optionally filtered by kind."""
    try:
        async with get_sessionmaker()() as session:
            stmt = select(AgentRun)
            if kind is not None:
                stmt = stmt.where(AgentRun.kind == kind)
            stmt = stmt.order_by(AgentRun.created_at.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [_to_record(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        log.warning("run list failed", kind=kind, error=str(exc))
        return []


async def touch_run(run_id: str) -> None:
    """Heartbeat: bump ``updated_at`` so the stuck-run sweeper knows this run is alive.
    A long-running handler calls this periodically while it works."""
    try:
        async with get_sessionmaker()() as session:
            row = await session.get(AgentRun, run_id)
            if row is not None:
                row.updated_at = _utc_now()
                await session.commit()
    except Exception as exc:  # noqa: BLE001 — a missed heartbeat must not break the run
        log.warning("run heartbeat failed", run_id=run_id, error=str(exc))


async def sweep_stuck_runs(ttl_seconds: int) -> int:
    """Fail `running` runs whose heartbeat (``updated_at``) is older than the TTL.

    Catches a worker that hung without either crashing (reconcile handles that) or
    finishing — otherwise the run stays `running` forever. Returns how many it failed.
    Timestamps are fixed-width UTC strings (see ``_fmt``), so the cutoff comparison is
    a plain ``<`` that matches chronological order.

    A single conditional ``UPDATE ... WHERE status='running'`` (not select-then-mutate)
    so a run that completes concurrently is not clobbered: if the handler's terminal
    write lands first the row is no longer ``running`` and this UPDATE skips it; if the
    sweep lands first the handler's authoritative write still wins. No lost update.
    """
    cutoff = _fmt(datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=ttl_seconds))
    try:
        async with get_sessionmaker()() as session:
            stmt = (
                update(AgentRun)
                .where(AgentRun.status == "running", AgentRun.updated_at < cutoff)
                .values(
                    status="failed",
                    error=f"no heartbeat for >{ttl_seconds}s — presumed dead",
                    updated_at=_utc_now(),
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            count = result.rowcount or 0
            if count:
                log.warning("swept stuck runs", count=count, ttl_s=ttl_seconds)
            return count
    except Exception as exc:  # noqa: BLE001
        log.warning("stuck-run sweep failed", error=str(exc))
        return 0


async def list_nonterminal_runs(limit: int = 1000) -> list[RunRecord]:
    """Runs still `pending`/`running` — used by the worker's startup reconciler to
    re-enqueue work orphaned by a crash (so a dropped job isn't lost forever)."""
    try:
        async with get_sessionmaker()() as session:
            stmt = (
                select(AgentRun)
                .where(AgentRun.status.in_(NON_TERMINAL_RUN_STATUSES))
                .order_by(AgentRun.created_at.asc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [_to_record(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        log.warning("nonterminal run list failed", error=str(exc))
        return []
