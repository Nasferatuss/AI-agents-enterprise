import httpx
import pytest

from workbench_gateway.app import create_app
from workbench_orchestrator import Step, WorkflowDef, register


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_list_workflows_includes_demo(client):
    resp = await client.get("/v1/workflows")
    assert resp.status_code == 200
    wf = next(w for w in resp.json() if w["name"] == "content_brief")
    assert wf["steps"] == ["validate", "draft", "review", "revise", "finalize"]


async def test_run_unknown_workflow_404(client):
    resp = await client.post("/v1/workflows/ghost/run", json={"input": {}})
    assert resp.status_code == 404


async def test_run_workflow_and_fetch_by_id(client):
    async def hello(state):
        return {"greeting": f"hello {state.get('name', 'world')}"}

    register(
        WorkflowDef(name="hello_wf", description="test", steps=[Step(name="hello", run=hello)])
    )

    resp = await client.post("/v1/workflows/hello_wf/run", json={"input": {"name": "ops"}})
    assert resp.status_code == 200
    run = resp.json()
    assert run["status"] == "completed"
    assert run["state"]["greeting"] == "hello ops"

    resp = await client.get(f"/v1/workflows/runs/{run['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == run["id"]

    resp = await client.get("/v1/workflows/runs")
    assert any(r["id"] == run["id"] for r in resp.json())
