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

from workbench_observability.db import get_sessionmaker
from workbench_observability.models import AgentRun
from workbench_observability.schema import RunRecord
from workbench_shared.logging import get_logger

log = get_logger(__name__)


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
            stmt = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)
            if kind is not None:
                stmt = stmt.where(AgentRun.kind == kind)
            rows = (await session.execute(stmt)).scalars().all()
            return [_to_record(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        log.warning("run list failed", kind=kind, error=str(exc))
        return []
