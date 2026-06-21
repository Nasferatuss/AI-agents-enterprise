"""Incident Response endpoints (mounted by the gateway).

Closes the loop with observability: it lists the failed runs the trace store
already captured and produces an RCA for any of them.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from workbench_app_incident.classify import classify
from workbench_app_incident.rca import RcaReport, analyze_incident
from workbench_observability import get_trace, list_traces
from workbench_runtime import get_router

router = APIRouter(prefix="/v1/apps/incidents", tags=["incident-response"])

_TERMINAL_OK = "completed"


class Incident(BaseModel):
    trace_id: str
    kind: str
    name: str
    status: str
    error: str | None
    root_cause: str


@router.get("", response_model=list[Incident])
async def incidents(limit: int = Query(default=50, ge=1, le=500)) -> list[Incident]:
    """Failed runs from the trace store (status != completed)."""
    out: list[Incident] = []
    for t in await list_traces(limit=limit):
        if t.status == _TERMINAL_OK:
            continue
        cause, _ = classify(t.kind, t.status, t.error)  # summary view (no payload)
        out.append(
            Incident(
                trace_id=t.id,
                kind=t.kind,
                name=t.name,
                status=t.status,
                error=t.error,
                root_cause=cause,
            )
        )
    return out


@router.post("/{trace_id}/rca", response_model=RcaReport)
async def rca(trace_id: str) -> RcaReport:
    trace = await get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"unknown trace: {trace_id}")
    return await analyze_incident(get_router(), trace)
