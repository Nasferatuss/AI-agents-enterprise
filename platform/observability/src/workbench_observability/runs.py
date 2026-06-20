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

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from workbench_observability.db import get_sessionmaker
from workbench_observability.models import AgentRun
from workbench_observability.schema import RunRecord
from workbench_shared.logging import get_logger

log = get_logger(__name__)

# In-flight statuses: a run that hasn't reached a terminal state yet. Used by the
# worker's startup reconciler to pick up runs orphaned by a crash.
NON_TERMINAL_RUN_STATUSES = ("pending", "running")


def _utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


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
    ISO-8601 timestamps sort chronologically as strings, so the comparison is a plain
    ``<`` on the stored value.
    """
    cutoff = (
        datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=ttl_seconds)
    ).isoformat()
    try:
        async with get_sessionmaker()() as session:
            stmt = select(AgentRun).where(
                AgentRun.status == "running", AgentRun.updated_at < cutoff
            )
            rows = (await session.execute(stmt)).scalars().all()
            for row in rows:
                row.status = "failed"
                row.error = f"no heartbeat for >{ttl_seconds}s — presumed dead"
                row.updated_at = _utc_now()
            await session.commit()
            if rows:
                log.warning("swept stuck runs", count=len(rows), ttl_s=ttl_seconds)
            return len(rows)
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
