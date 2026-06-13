"""Trace recording and queries."""

import datetime
import uuid
from collections import Counter

from sqlalchemy import select

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
    async with get_sessionmaker()() as session:
        rows = (await session.execute(select(Trace))).scalars().all()

    total = len(rows)
    successful = sum(1 for r in rows if r.status in SUCCESS_STATUSES)
    by_kind = Counter(r.kind for r in rows)
    failures = Counter((r.kind, r.status) for r in rows if r.status not in SUCCESS_STATUSES)
    return TraceAggregates(
        total=total,
        success_rate=successful / total if total else 0.0,
        total_cost_usd=round(sum(r.cost_usd or 0.0 for r in rows), 6),
        p95_latency_ms=_p95([r.latency_ms for r in rows]),
        by_kind=dict(by_kind),
        failures=[
            FailureBucket(kind=k, status=s, count=c)
            for (k, s), c in sorted(failures.items(), key=lambda kv: kv[1], reverse=True)
        ],
    )
