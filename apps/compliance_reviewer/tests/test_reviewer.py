import json
from pathlib import Path

import httpx

from workbench_app_compliance.reviewer import review_document
from workbench_runtime.providers import Provider
from workbench_runtime.router import ModelRouter

_CLEAN_DOC = (
    Path(__file__).resolve().parents[3] / "examples" / "docs" / "clean_policy.md"
).read_text()


def _router(text: str | None) -> ModelRouter:
    """text=None → no provider (simulates LLM unavailable)."""
    if text is None:
        router = ModelRouter(registry={})
        router.chain = lambda complexity: []  # type: ignore[method-assign]
        return router
    payload = {
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 30, "completion_tokens": 15},
    }
    handler = lambda request: httpx.Response(200, json=payload)  # noqa: E731
    provider = Provider(
        name="fake",
        kind="openai_compatible",
        base_url="http://fake/v1",
        api_key_env="",
        models={"default": "fake-model"},
    )
    router = ModelRouter(
        registry={"fake": provider},
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    router.chain = lambda complexity: [("fake", "default")]  # type: ignore[method-assign]
    return router


async def test_review_combines_deterministic_findings_with_llm_narrative():
    doc = "Stores SSN 123-45-6789 and uses shared credentials. Disable encryption in staging."
    narrative = json.dumps(
        {"summary": "High risk: PII and weak controls.", "recommendations": ["Encrypt staging"]}
    )
    report = await review_document(_router(narrative), doc)

    # deterministic part
    assert report.risk_band in ("high", "critical")
    assert any(f.type == "ssn" for f in report.pii_findings)
    assert any(v.rule_id == "no-share-credentials" for v in report.policy_violations)
    # llm narrative
    assert report.summary.startswith("High risk")
    assert report.recommendations == ["Encrypt staging"]


async def test_review_works_without_a_provider():
    doc = "Stores SSN 123-45-6789."
    report = await review_document(_router(None), doc)
    # deterministic findings still produced; narrative empty
    assert report.risk_score > 0
    assert any(f.type == "ssn" for f in report.pii_findings)
    assert report.summary == ""
    assert report.recommendations == []


async def test_clean_document_scores_low():
    report = await review_document(_router(None), _CLEAN_DOC)
    assert report.risk_score == 0
    assert report.risk_band == "low"
