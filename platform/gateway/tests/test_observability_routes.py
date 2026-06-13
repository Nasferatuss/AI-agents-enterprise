import httpx
import pytest

from workbench_gateway.app import create_app
from workbench_observability import init_db
from workbench_orchestrator import Step, WorkflowDef, register


@pytest.fixture
async def client():
    await init_db()  # ASGITransport doesn't run lifespan; init the (in-memory) store here

    async def noop(state):
        return {"done": True}

    register(WorkflowDef(name="obs_demo", description="", steps=[Step(name="s", run=noop)]))

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_workflow_run_is_recorded_and_queryable(client):
    # run a no-LLM workflow → it should be recorded as a trace
    run = (await client.post("/v1/workflows/obs_demo/run", json={"input": {}})).json()
    assert run["status"] == "completed"

    traces = (await client.get("/v1/observability/traces")).json()
    assert len(traces) == 1
    t = traces[0]
    assert t["kind"] == "workflow"
    assert t["name"] == "obs_demo"
    assert t["status"] == "completed"

    detail = (await client.get(f"/v1/observability/traces/{t['id']}")).json()
    assert detail["payload"]["state"]["done"] is True


async def test_summary_reports_aggregates(client):
    await client.post("/v1/workflows/obs_demo/run", json={"input": {}})
    await client.post("/v1/workflows/obs_demo/run", json={"input": {}})

    summary = (await client.get("/v1/observability/summary")).json()
    assert summary["total"] == 2
    assert summary["success_rate"] == 1.0
    assert summary["by_kind"]["workflow"] == 2


async def test_awaiting_approval_run_is_not_traced(client):
    async def prep(state):
        return {}

    register(
        WorkflowDef(
            name="obs_gate",
            description="",
            steps=[Step(name="g", run=prep, requires_approval=True)],
        )
    )
    run = (await client.post("/v1/workflows/obs_gate/run", json={"input": {}})).json()
    assert run["status"] == "awaiting_approval"

    # paused run must NOT appear as a trace yet
    traces = (await client.get("/v1/observability/traces?kind=workflow")).json()
    assert all(t["name"] != "obs_gate" for t in traces)

    # after approval it reaches a terminal state → now traced
    await client.post(f"/v1/workflows/runs/{run['id']}/approve", json={"actor": "x"})
    traces = (await client.get("/v1/observability/traces?kind=workflow")).json()
    assert any(t["name"] == "obs_gate" and t["status"] == "completed" for t in traces)


async def test_unknown_trace_404(client):
    resp = await client.get("/v1/observability/traces/nope")
    assert resp.status_code == 404
