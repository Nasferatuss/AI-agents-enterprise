import json

import httpx
import pytest

from workbench_app_process import api as process_api
from workbench_gateway.app import create_app
from workbench_runtime.providers import Provider
from workbench_runtime.router import ModelRouter


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _stub_router(text: str) -> ModelRouter:
    payload = {
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 40, "completion_tokens": 20},
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


async def test_process_analyze(client, monkeypatch):
    analysis = json.dumps(
        {
            "entities": [{"name": "HR", "type": "actor"}],
            "steps": [{"id": 1, "actor": "HR", "action": "create record", "next": []}],
            "contradictions": ["unclear contractor approval"],
            "backlog": [{"title": "Define approver", "priority": "high"}],
        }
    )
    monkeypatch.setattr(process_api, "get_router", lambda: _stub_router(analysis))
    resp = await client.post("/v1/apps/process/analyze", json={"document": "a spec"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["backlog"][0]["title"] == "Define approver"
    assert "flowchart TD" in body["mermaid"]


async def test_process_analyze_503_without_provider(client):
    resp = await client.post("/v1/apps/process/analyze", json={"document": "a spec"})
    assert resp.status_code == 503  # no provider configured in the test env


async def test_compliance_review_deterministic_without_provider(client):
    # the compliance reviewer returns findings even with no LLM available
    doc = "Stores SSN 123-45-6789 and uses shared credentials. Disable encryption."
    resp = await client.post("/v1/apps/compliance/review", json={"document": doc})
    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_band"] in ("high", "critical")
    assert any(f["type"] == "ssn" for f in body["pii_findings"])
    assert any(v["rule_id"] == "no-share-credentials" for v in body["policy_violations"])


async def test_compliance_oversized_document_rejected(client):
    resp = await client.post("/v1/apps/compliance/review", json={"document": "x" * 25000})
    assert resp.status_code == 422
