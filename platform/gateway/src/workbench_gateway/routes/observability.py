"""Observability endpoints: list traces, trace detail, dashboard summary."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from workbench_observability import (
    TraceAggregates,
    TraceDetail,
    TraceSummary,
    aggregates,
    get_trace,
    list_traces,
)

router = APIRouter(prefix="/v1/observability", tags=["observability"])

Kind = Literal["agent", "workflow", "eval"]


@router.get("/summary", response_model=TraceAggregates)
async def summary() -> TraceAggregates:
    return await aggregates()


@router.get("/traces", response_model=list[TraceSummary])
async def traces(
    kind: Kind | None = None, limit: int = Query(default=50, ge=1, le=500)
) -> list[TraceSummary]:
    return await list_traces(kind=kind, limit=limit)


@router.get("/traces/{trace_id}", response_model=TraceDetail)
async def trace(trace_id: str) -> TraceDetail:
    detail = await get_trace(trace_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"unknown trace: {trace_id}")
    return detail
