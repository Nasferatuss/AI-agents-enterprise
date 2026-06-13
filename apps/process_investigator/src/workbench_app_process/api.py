"""Business Process Investigator endpoints (mounted by the gateway)."""

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from workbench_app_process.analyzer import ProcessAnalysisError, ProcessReport, analyze_document
from workbench_observability import safe_record
from workbench_runtime import get_router
from workbench_runtime.router import NoProviderAvailableError

router = APIRouter(prefix="/v1/apps/process", tags=["process-investigator"])


class AnalyzeRequest(BaseModel):
    document: str = Field(min_length=1, max_length=20000)


@router.post("/analyze", response_model=ProcessReport)
async def analyze(req: AnalyzeRequest) -> ProcessReport:
    started = time.monotonic()
    try:
        report = await analyze_document(get_router(), req.document)
    except NoProviderAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProcessAnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await safe_record(
        kind="agent",
        name="process_investigator",
        status="completed",
        latency_ms=int((time.monotonic() - started) * 1000),
        cost_usd=report.cost_usd,
        num_steps=len(report.steps),
        payload=report.model_dump(),
    )
    return report
