import json

import httpx
import pytest

from workbench_app_process import api as process_api
from workbench_app_research import api as research_api
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


# --- deep research / tool gateway ---


async def test_research_tools_registry(client):
    resp = await client.get("/v1/apps/research/tools")
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()}
    assert names == {"web_search", "fetch", "kb_search"}


async def test_research_503_without_provider(client):
    resp = await client.post("/v1/apps/research", json={"question": "what is RAG?"})
    assert resp.status_code == 503


async def test_research_produces_cited_report(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        system = next(m["content"] for m in body["messages"] if m["role"] == "system")
        text = (
            json.dumps({"sub_questions": ["what is retrieval augmented generation"]})
            if "research planner" in system
            else "RAG grounds the model in documents [1]."
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": text}}],
                "usage": {"prompt_tokens": 40, "completion_tokens": 20},
            },
        )

    provider = Provider(
        name="fake",
        kind="openai_compatible",
        base_url="http://fake/v1",
        api_key_env="",
        models={"default": "fake-model"},
    )

    def stub():
        r = ModelRouter(
            registry={"fake": provider},
            http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        r.chain = lambda complexity: [("fake", "default")]  # type: ignore[method-assign]
        return r

    monkeypatch.setattr(research_api, "get_router", stub)
    resp = await client.post("/v1/apps/research", json={"question": "what is RAG?"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["sources"]) >= 1
    assert {a["tool"] for a in body["tool_calls"]} >= {"web_search", "fetch"}
    assert "[1]" in body["report"]
