import httpx
import pytest

from workbench_gateway.app import create_app
from workbench_orchestrator import Step, WorkflowDef, register


@pytest.fixture(autouse=True)
def _register_gated_workflow():
    async def prepare(state):
        return {"prepared": True}

    async def act(state):
        return {"acted": True}

    register(
        WorkflowDef(
            name="gated_demo",
            description="test gate",
            steps=[
                Step(name="prepare", run=prepare, next="act"),
                Step(
                    name="act",
                    run=act,
                    next=None,
                    requires_approval=True,
                    approval_prompt="Proceed?",
                ),
            ],
        )
    )


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_list_reports_approval_gates(client):
    resp = await client.get("/v1/workflows")
    wf = next(w for w in resp.json() if w["name"] == "gated_demo")
    assert wf["approval_gates"] == ["act"]


async def test_run_pauses_then_approve_completes(client):
    resp = await client.post("/v1/workflows/gated_demo/run", json={"input": {}})
    run = resp.json()
    assert run["status"] == "awaiting_approval"
    assert run["pending_step"] == "act"
    assert run["approval_prompt"] == "Proceed?"
    assert "acted" not in run["state"]

    resp = await client.post(
        f"/v1/workflows/runs/{run['id']}/approve", json={"actor": "ops", "reason": "ok"}
    )
    assert resp.status_code == 200
    done = resp.json()
    assert done["status"] == "completed"
    assert done["state"]["acted"] is True
    assert done["approvals"][0]["actor"] == "ops"


async def test_run_pauses_then_reject(client):
    run = (await client.post("/v1/workflows/gated_demo/run", json={"input": {}})).json()
    resp = await client.post(f"/v1/workflows/runs/{run['id']}/reject", json={"actor": "ops"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rejected"
    assert "acted" not in body["state"]


async def test_approve_unknown_run_404(client):
    resp = await client.post("/v1/workflows/runs/nope/approve", json={"actor": "x"})
    assert resp.status_code == 404


async def test_double_approve_409(client):
    run = (await client.post("/v1/workflows/gated_demo/run", json={"input": {}})).json()
    await client.post(f"/v1/workflows/runs/{run['id']}/approve", json={"actor": "x"})
    resp = await client.post(f"/v1/workflows/runs/{run['id']}/approve", json={"actor": "x"})
    assert resp.status_code == 409
