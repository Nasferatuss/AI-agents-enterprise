"""Autonomous Agent endpoints (mounted by the gateway).

Exposes the plan→act→reflect→repeat engine (agent.py) over HTTP.
"""

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from workbench_app_autonomous.agent import AutonomousResult, run_autonomous
from workbench_observability import safe_record
from workbench_runtime import get_router
from workbench_runtime.router import NoProviderAvailableError

router = APIRouter(prefix="/v1/apps/autonomous", tags=["autonomous-agent"])


class RunRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.post("/run", response_model=AutonomousResult)
async def run(req: RunRequest) -> AutonomousResult:
    started = time.monotonic()
    try:
        result = await run_autonomous(get_router(), req.goal)
    except NoProviderAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await safe_record(
        kind="agent",
        name="autonomous_agent",
        status="completed" if result.completed else "max_steps_reached",
        latency_ms=int((time.monotonic() - started) * 1000),
        cost_usd=result.cost_usd,
        num_steps=len(result.iterations),
        payload=result.model_dump(),
    )
    return result
