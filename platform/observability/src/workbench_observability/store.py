"""Trace recording and queries."""

import datetime
import uuid

from sqlalchemy import case, func, select

from workbench_observability.db import get_sessionmaker
from workbench_observability.models import Trace
from workbench_observability.schema import (
    NON_TERMINAL_STATUSES,
    SUCCESS_STATUSES,
    FailureBucket,
    TraceAggregates,
    TraceDetail,
    TraceSummary,
)
from workbench_shared.logging import get_logger

log = get_logger(__name__)


def _utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()  # microsecond → stable sort


async def safe_record(**kwargs) -> str | None:
    """Best-effort record: a trace-store outage must never break the user's
    request, so failures are logged loudly and swallowed (telemetry, not the
    critical path). Domain packages call this from their HTTP routes."""
    try:
        return await record_trace(**kwargs)
    except Exception as exc:  # noqa: BLE001 — telemetry must not break the request
        log.warning("trace recording failed", kind=kwargs.get("kind"), error=str(exc))
        return None


async def record_trace(
    *,
    kind: str,
    name: str,
    status: str,
    latency_ms: int = 0,
    cost_usd: float | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    num_steps: int = 0,
    error: str | None = None,
    payload: dict,
) -> str | None:
    """Persist one trace. Returns the trace id, or None if the run is non-terminal."""
    if status in NON_TERMINAL_STATUSES:
        return None
    trace_id = uuid.uuid4().hex[:16]
    async with get_sessionmaker()() as session:
        session.add(
            Trace(
                id=trace_id,
                kind=kind,
                name=name,
                status=status,
                created_at=_utc_now(),
                latency_ms=latency_ms,
                cost_usd=cost_usd,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                num_steps=num_steps,
                error=error,
                payload=payload,
            )
        )
        await session.commit()
    return trace_id


async def record_tool_audit(entry: dict) -> str | None:
    """Persist one Tool Gateway audit entry as a trace (durable governance log).

    The Tool Gateway's in-memory audit list is ephemeral (the gateway is recreated
    per request). An app wires this as the gateway's `audit_sink` so every allowed /
    denied tool call survives. We keep this helper here — rather than importing
    observability inside toolgateway — to avoid a toolgateway→observability cycle.

    `entry` is an `AuditEntry`-shaped dict: tool, args, allowed, error, latency_ms, at.
    A denied call (`allowed is False`) is recorded with status "denied"; an allowed
    call is "failed" if it carried an error, else "completed".
    """
    allowed = entry.get("allowed", True)
    error = entry.get("error")
    if not allowed:
        status = "denied"
    elif error:
        status = "failed"
    else:
        status = "completed"
    return await safe_record(
        kind="tool",
        name=entry.get("tool", "unknown"),
        status=status,
        latency_ms=entry.get("latency_ms", 0),
        error=error,
        payload={"args": entry.get("args", {}), "at": entry.get("at")},
    )


async def list_traces(kind: str | None = None, limit: int = 50) -> list[TraceSummary]:
    stmt = select(Trace).order_by(Trace.created_at.desc()).limit(limit)
    if kind:
        stmt = stmt.where(Trace.kind == kind)
    async with get_sessionmaker()() as session:
        rows = (await session.execute(stmt)).scalars().all()
        return [TraceSummary.model_validate(r) for r in rows]


async def get_trace(trace_id: str) -> TraceDetail | None:
    async with get_sessionmaker()() as session:
        row = await session.get(Trace, trace_id)
        return TraceDetail.model_validate(row) if row else None


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(len(ordered) * 0.95))
    return ordered[idx]


async def aggregates() -> TraceAggregates:
    """Dashboard rollups, computed in SQL rather than by loading every trace.

    Counts, sums and groupings are pushed down via `func.count` / `group_by` so we
    never materialize all rows just to tally them. The p95 latency is computed in SQL
    via `percentile_cont` on Postgres; sqlite has no percentile function, so there we
    fall back to fetching just the latency column and computing it in Python.
    """
    is_success = Trace.status.in_(SUCCESS_STATUSES)
    async with get_sessionmaker()() as session:
        backend = session.bind.dialect.name

        # Scalar rollups: total, successes, total cost — one round-trip, no row load.
        totals = (
            await session.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(case((is_success, 1), else_=0)), 0),
                    func.coalesce(func.sum(Trace.cost_usd), 0.0),
                )
            )
        ).one()
        total, successful, total_cost = int(totals[0]), int(totals[1]), float(totals[2])

        # Counts grouped by kind.
        by_kind = {
            kind: int(count)
            for kind, count in (
                await session.execute(select(Trace.kind, func.count()).group_by(Trace.kind))
            ).all()
        }

        # Failure taxonomy: non-success runs grouped by (kind, status), most common first.
        failure_rows = (
            await session.execute(
                select(Trace.kind, Trace.status, func.count())
                .where(~is_success)
                .group_by(Trace.kind, Trace.status)
                .order_by(func.count().desc())
            )
        ).all()

        # p95 latency — in SQL on Postgres; Python fallback elsewhere (e.g. sqlite).
        if backend == "postgresql":
            p95 = (
                await session.execute(
                    select(func.percentile_cont(0.95).within_group(Trace.latency_ms.asc()))
                )
            ).scalar()
            p95_latency = int(p95) if p95 is not None else 0
        else:
            latencies = (await session.execute(select(Trace.latency_ms))).scalars().all()
            p95_latency = _p95(list(latencies))

    return TraceAggregates(
        total=total,
        success_rate=successful / total if total else 0.0,
        total_cost_usd=round(total_cost, 6),
        p95_latency_ms=p95_latency,
        by_kind=by_kind,
        failures=[FailureBucket(kind=k, status=s, count=int(c)) for k, s, c in failure_rows],
    )
