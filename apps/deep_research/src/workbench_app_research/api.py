"""Deep Research Agent endpoints (mounted by the gateway)."""

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from workbench_app_research.research import ResearchReport, run_research
from workbench_observability import safe_record
from workbench_runtime import get_router
from workbench_runtime.router import NoProviderAvailableError
from workbench_toolgateway import ToolSpec, build_default_gateway

router = APIRouter(prefix="/v1/apps/research", tags=["deep-research"])


class ResearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@router.get("/tools", response_model=list[ToolSpec])
async def tools() -> list[ToolSpec]:
    """The tools the gateway exposes (registry view)."""
    return build_default_gateway().list_tools()


@router.post("", response_model=ResearchReport)
async def research(req: ResearchRequest) -> ResearchReport:
    started = time.monotonic()
    gateway = build_default_gateway()  # fresh per request → clean audit log
    try:
        report = await run_research(get_router(), gateway, req.question)
    except NoProviderAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await safe_record(
        kind="agent",
        name="deep_research",
        status="completed",
        latency_ms=int((time.monotonic() - started) * 1000),
        cost_usd=report.cost_usd,
        num_steps=len(report.tool_calls),
        payload=report.model_dump(),
    )
    return report
