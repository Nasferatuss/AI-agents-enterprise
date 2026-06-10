import httpx
import pytest

from workbench_gateway.app import create_app
from workbench_gateway.routes import agents as agents_route
from workbench_runtime.types import AgentRun, Usage


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_list_agents_exposes_demo(client):
    resp = await client.get("/v1/agents")
    assert resp.status_code == 200
    demo = next(a for a in resp.json() if a["name"] == "demo")
    assert set(demo["tools"]) == {"calculator", "utc_now"}


async def test_run_unknown_agent_404(client):
    resp = await client.post("/v1/agents/ghost/run", json={"input": "hi"})
    assert resp.status_code == 404


async def test_run_agent_returns_run(client, monkeypatch):
    async def stub_run(agent, user_input):
        return AgentRun(
            agent=agent.name,
            status="completed",
            final_text=f"ran: {user_input}",
            steps=[],
            usage=Usage(input_tokens=1, output_tokens=1),
            cost_usd=0.0,
        )

    monkeypatch.setattr(agents_route, "run_agent", stub_run)
    resp = await client.post("/v1/agents/demo/run", json={"input": "2+2?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["final_text"] == "ran: 2+2?"
