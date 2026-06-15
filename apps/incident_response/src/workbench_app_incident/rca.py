"""RCA report: deterministic root cause + LLM narrative for a failed run.

Mirrors the compliance pattern — the root-cause category and evidence are
deterministic; the LLM only writes the human-readable summary and the fix
recommendation. Returns the structured report even with no provider.
"""

import json

from pydantic import BaseModel

from workbench_app_incident.classify import RootCause, classify
from workbench_observability import TraceDetail
from workbench_runtime.router import ModelRouter, NoProviderAvailableError
from workbench_runtime.types import UserMessage

_SYSTEM = (
    "You are an SRE doing incident response on an AI agent run. Given the failure "
    "and its auto-detected root cause, write a brief RCA. Respond with ONLY JSON: "
    '{"summary": "<what happened, one or two sentences>", '
    '"recommendation": "<the concrete fix>"}'
)


class RcaReport(BaseModel):
    trace_id: str
    kind: str
    name: str
    status: str
    root_cause: RootCause
    signals: list[str]
    summary: str = ""  # LLM narrative (best-effort)
    recommendation: str = ""
    provider: str = ""
    cost_usd: float | None = None


async def analyze_incident(router: ModelRouter, trace: TraceDetail) -> RcaReport:
    cause, signals = classify(trace.kind, trace.status, trace.error, trace.payload)
    report = RcaReport(
        trace_id=trace.id,
        kind=trace.kind,
        name=trace.name,
        status=trace.status,
        root_cause=cause,
        signals=signals,
    )

    prompt = (
        f"Run: {trace.name} (kind={trace.kind})\n"
        f"Status: {trace.status}\n"
        f"Error: {trace.error or 'none'}\n"
        f"Auto root cause: {cause}\n"
        f"Signals: {'; '.join(signals)}"
    )
    try:
        out = await router.step(
            [UserMessage(content=prompt)],
            complexity="standard",
            system=_SYSTEM,
            max_tokens=512,
        )
    except NoProviderAvailableError:
        return report

    report.provider, report.cost_usd = out.provider, out.cost_usd
    start, end = out.text.find("{"), out.text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(out.text[start : end + 1])
            report.summary = str(data.get("summary", ""))
            report.recommendation = str(data.get("recommendation", ""))
        except json.JSONDecodeError:
            pass
    return report
