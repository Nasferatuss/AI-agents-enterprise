import json

import httpx
import pytest

from workbench_app_incident.classify import classify
from workbench_app_incident.rca import analyze_incident
from workbench_observability import TraceDetail
from workbench_runtime.providers import Provider
from workbench_runtime.router import ModelRouter

# --- deterministic classification ---


@pytest.mark.parametrize(
    "kind,status,error,payload,expected",
    [
        ("workflow", "rejected", "rejected by bob", {}, "policy_rejection"),
        ("agent", "max_steps_reached", "max_steps_reached", {}, "loop_no_progress"),
        ("agent", "failed", "no provider succeeded", {}, "provider_unavailable"),
        # the router's actual client-safe message must classify the same way
        ("agent", "failed", "no model provider is currently available", {}, "provider_unavailable"),
        ("agent", "failed", "execution failed: no such column", {}, "sql_error"),
        ("agent", "failed", "2 scenario(s) failed", {}, "scenario_failures"),
        ("eval", "failed", "low quality", {"aggregates": {"hit_rate": 0.3}}, "low_eval_quality"),
        ("agent", "failed", None, {"tool_calls": [{"allowed": False}]}, "tool_denied"),
        ("agent", "failed", "weird", {}, "unknown"),
    ],
)
def test_classify(kind, status, error, payload, expected):
    cause, signals = classify(kind, status, error, payload)
    assert cause == expected
    assert signals  # always some evidence


# --- RCA report ---


def _router(text: str | None) -> ModelRouter:
    if text is None:
        r = ModelRouter(registry={})
        r.chain = lambda complexity: []  # type: ignore[method-assign]
        return r
    handler = lambda request: httpx.Response(  # noqa: E731
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10},
        },
    )
    provider = Provider(
        name="fake",
        kind="openai_compatible",
        base_url="http://fake/v1",
        api_key_env="",
        models={"default": "fake-model"},
    )
    r = ModelRouter(
        registry={"fake": provider}, http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    r.chain = lambda complexity: [("fake", "default")]  # type: ignore[method-assign]
    return r


def _trace(**kw) -> TraceDetail:
    base = dict(
        id="t1",
        kind="agent",
        name="text2sql",
        status="failed",
        created_at="2026-06-13T00:00:00",
        latency_ms=600,
        cost_usd=None,
        input_tokens=0,
        output_tokens=0,
        num_steps=1,
        error="execution failed: no such column",
        payload={},
    )
    return TraceDetail(**{**base, **kw})


async def test_rca_deterministic_cause_plus_llm_narrative():
    narrative = json.dumps(
        {"summary": "A bad column reference.", "recommendation": "Validate schema."}
    )
    report = await analyze_incident(_router(narrative), _trace())
    assert report.root_cause == "sql_error"
    assert report.signals
    assert report.summary == "A bad column reference."
    assert report.recommendation == "Validate schema."


async def test_rca_without_provider_keeps_structured_cause():
    report = await analyze_incident(
        _router(None), _trace(status="rejected", kind="workflow", error="rejected by bob")
    )
    assert report.root_cause == "policy_rejection"
    assert report.summary == ""  # no LLM narrative, but the classification stands
