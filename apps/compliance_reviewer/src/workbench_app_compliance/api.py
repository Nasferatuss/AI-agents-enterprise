"""Compliance & Risk Reviewer endpoints (mounted by the gateway)."""

import time

from fastapi import APIRouter
from pydantic import BaseModel, Field

from workbench_app_compliance.reviewer import RiskReport, review_document
from workbench_observability import safe_record
from workbench_runtime import get_router

router = APIRouter(prefix="/v1/apps/compliance", tags=["compliance-reviewer"])


class ReviewRequest(BaseModel):
    document: str = Field(min_length=1, max_length=20000)


@router.post("/review", response_model=RiskReport)
async def review(req: ReviewRequest) -> RiskReport:
    started = time.monotonic()
    report = await review_document(get_router(), req.document)
    await safe_record(
        kind="agent",
        name="compliance_reviewer",
        status="completed",
        latency_ms=int((time.monotonic() - started) * 1000),
        cost_usd=report.cost_usd,
        num_steps=len(report.policy_violations) + len(report.pii_findings),
        error=None if report.risk_band in ("low", "medium") else report.risk_band,
        payload=report.model_dump(),
    )
    return report
