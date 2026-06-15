"""Risk reviewer: deterministic findings + LLM narrative → a risk report.

The score and band come from the policy engine (reproducible). The LLM is given
the findings and writes a plain-language summary and recommendations — it never
sets the score. If no provider is available the report still returns with the
deterministic findings and an empty narrative.
"""

import json

from pydantic import BaseModel

from workbench_app_compliance.policy import (
    DEFAULT_RULES,
    PiiFinding,
    PolicyRule,
    PolicyViolation,
    RiskBand,
    check_policies,
    scan_pii,
    score_risk,
)
from workbench_runtime.router import ModelRouter, NoProviderAvailableError
from workbench_runtime.types import UserMessage

_SYSTEM = (
    "You are a compliance officer. You are given automated findings (PII matches "
    "and policy-rule violations) for a document. Write a short risk summary and "
    "concrete remediation recommendations. Do NOT invent findings beyond those "
    'given. Respond with ONLY JSON: {"summary": "...", "recommendations": ["..."]}'
)


class RiskReport(BaseModel):
    risk_score: int  # 0–100, deterministic
    risk_band: RiskBand  # deterministic
    pii_findings: list[PiiFinding]
    policy_violations: list[PolicyViolation]
    summary: str = ""  # LLM narrative (best-effort)
    recommendations: list[str] = []
    provider: str = ""
    model: str = ""
    cost_usd: float | None = None


def _findings_brief(pii: list[PiiFinding], violations: list[PolicyViolation]) -> str:
    pii_str = ", ".join(f"{f.count}× {f.type}" for f in pii) or "none"
    vio_str = "; ".join(f"[{v.severity}] {v.description}" for v in violations) or "none"
    return f"PII detected: {pii_str}\nPolicy violations: {vio_str}"


async def review_document(
    router: ModelRouter, document: str, rules: list[PolicyRule] | None = None
) -> RiskReport:
    rules = rules if rules is not None else DEFAULT_RULES
    pii = scan_pii(document)
    violations = check_policies(document, rules)
    score, band = score_risk(pii, violations)
    report = RiskReport(
        risk_score=score, risk_band=band, pii_findings=pii, policy_violations=violations
    )

    prompt = f"{_findings_brief(pii, violations)}\n\nRisk score: {score}/100 ({band})."
    try:
        out = await router.step(
            [UserMessage(content=prompt)],
            complexity="standard",
            system=_SYSTEM,
            max_tokens=768,
        )
    except NoProviderAvailableError:
        return report  # deterministic findings stand on their own

    report.provider, report.model, report.cost_usd = out.provider, out.model, out.cost_usd
    start, end = out.text.find("{"), out.text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(out.text[start : end + 1])
            report.summary = str(data.get("summary", ""))
            report.recommendations = [str(r) for r in data.get("recommendations", [])]
        except json.JSONDecodeError:
            pass
    return report
