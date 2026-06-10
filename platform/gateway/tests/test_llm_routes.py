import httpx
import pytest

from workbench_gateway.app import create_app
from workbench_gateway.routes import llm
from workbench_runtime.router import NoProviderAvailableError
from workbench_runtime.types import Completion, Usage


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_list_models_exposes_registry(client):
    resp = await client.get("/v1/models")
    assert resp.status_code == 200
    providers = {p["name"]: p for p in resp.json()}
    assert providers["local"]["enabled"] is True  # no key required
    assert {"anthropic", "openai", "deepseek", "kimi"} <= providers.keys()


async def test_chat_routes_through_router(client, monkeypatch):
    class StubRouter:
        async def complete(self, messages, complexity, system, max_tokens):
            return Completion(
                text="stubbed",
                provider="local",
                model="qwen2.5:3b-instruct",
                usage=Usage(input_tokens=3, output_tokens=2),
                cost_usd=0.0,
                latency_ms=7,
                complexity=complexity,
            )

    monkeypatch.setattr(llm, "get_router", lambda: StubRouter())
    resp = await client.post(
        "/v1/chat",
        json={"messages": [{"role": "user", "content": "ping"}], "complexity": "simple"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "stubbed"
    assert body["complexity"] == "simple"


async def test_chat_503_when_no_provider(client, monkeypatch):
    class FailingRouter:
        async def complete(self, **kwargs):
            raise NoProviderAvailableError("standard", [])

    monkeypatch.setattr(llm, "get_router", lambda: FailingRouter())
    resp = await client.post("/v1/chat", json={"messages": [{"role": "user", "content": "x"}]})
    assert resp.status_code == 503
