"""Guarded Computer-Use QA endpoints (mounted by the gateway)."""

import time

from fastapi import APIRouter
from pydantic import BaseModel

from workbench_app_cua.runner import QAReport, run_qa
from workbench_app_cua.sandbox import UiSession
from workbench_app_cua.scenarios import SCENARIOS, scenario_names
from workbench_observability import safe_record
from workbench_runtime import get_router
from workbench_runtime.router import NoProviderAvailableError
from workbench_runtime.types import UserMessage

router = APIRouter(prefix="/v1/apps/cua", tags=["computer-use-qa"])

_NARRATE_SYSTEM = (
    "You are a QA engineer. Given automated test results for a legacy web UI, "
    "write a short bug report: what passed, what failed, and the impact of each "
    "bug. Use ONLY the findings provided. Plain text, a few sentences."
)


class ScenarioInfo(BaseModel):
    name: str
    description: str


@router.get("/scenarios", response_model=list[ScenarioInfo])
async def scenarios() -> list[ScenarioInfo]:
    return [ScenarioInfo(name=s.name, description=s.description) for s in SCENARIOS]


@router.get("/screen")
async def screen() -> dict:
    """The initial sandbox screen (a 'screenshot' of the legacy UI)."""
    return UiSession().observe().model_dump()


async def _narrate(report: QAReport) -> None:
    if not report.bugs:
        return
    findings = f"{report.passed} passed, {report.failed} failed.\nBugs:\n" + "\n".join(
        f"- [{b.scenario}] expected {b.expected}; got {b.actual}" for b in report.bugs
    )
    try:
        out = await get_router().step(
            [UserMessage(content=findings)],
            complexity="standard",
            system=_NARRATE_SYSTEM,
            max_tokens=512,
        )
    except NoProviderAvailableError:
        return  # deterministic results stand on their own
    report.summary, report.provider, report.cost_usd = out.text, out.provider, out.cost_usd


@router.post("/run", response_model=QAReport)
async def run() -> QAReport:
    started = time.monotonic()
    report = await run_qa(SCENARIOS)
    await _narrate(report)
    await safe_record(
        kind="agent",
        name="computer_use_qa",
        status="completed" if report.failed == 0 else "failed",
        latency_ms=int((time.monotonic() - started) * 1000),
        cost_usd=report.cost_usd,
        num_steps=len(report.action_trace),
        error=None if report.failed == 0 else f"{report.failed} scenario(s) failed",
        payload=report.model_dump(),
    )
    return report


# names exported for tests / discovery
SCENARIO_NAMES = scenario_names()
