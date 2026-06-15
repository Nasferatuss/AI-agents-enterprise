"""Compliance & Risk Reviewer endpoints (mounted by the gateway)."""

import io
import time
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from workbench_app_compliance.reviewer import RiskReport, review_document
from workbench_observability import safe_record
from workbench_runtime import get_router

router = APIRouter(prefix="/v1/apps/compliance", tags=["compliance-reviewer"])

_MAX_DOC_LEN = 20000  # mirrors ReviewRequest.document max_length


class ReviewRequest(BaseModel):
    document: str = Field(min_length=1, max_length=_MAX_DOC_LEN)


def _extract_text(filename: str, content_type: str, data: bytes) -> str:
    """File bytes → plain text, dispatched on extension. Raises 415 if unsupported."""
    name = (filename or "").lower()
    if name.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="replace")
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if name.endswith(".docx"):
        import docx

        document = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in document.paragraphs)
    raise HTTPException(
        status_code=415,
        detail=f"unsupported file type: {filename!r} (allowed: .txt, .md, .pdf, .docx)",
    )


async def _run_review(document: str) -> RiskReport:
    started = time.monotonic()
    report = await review_document(get_router(), document)
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


@router.post("/review", response_model=RiskReport)
async def review(req: ReviewRequest) -> RiskReport:
    return await _run_review(req.document)


@router.post("/review/file", response_model=RiskReport)
async def review_file(file: Annotated[UploadFile, File()]) -> RiskReport:
    text = _extract_text(file.filename or "", file.content_type or "", await file.read())
    if not text.strip():
        raise HTTPException(status_code=422, detail="could not extract any text from the file")
    return await _run_review(text[:_MAX_DOC_LEN])  # bound like ReviewRequest.document
