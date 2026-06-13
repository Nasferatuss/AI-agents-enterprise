import httpx
import pytest

from workbench_gateway.app import create_app
from workbench_observability import init_db, record_trace


@pytest.fixture
async def client():
    await init_db()
    # seed a couple of failed traces + one healthy run
    await record_trace(
        kind="workflow",
        name="access_request",
        status="rejected",
        error="rejected by ops",
        payload={},
    )
    await record_trace(
        kind="agent",
        name="text2sql",
        status="failed",
        error="execution failed: no such column",
        payload={},
    )
    await record_trace(kind="agent", name="demo", status="completed", payload={})

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_incidents_lists_only_failures_with_root_cause(client):
    items = (await client.get("/v1/apps/incidents")).json()
    names = {(i["name"], i["root_cause"]) for i in items}
    assert ("access_request", "policy_rejection") in names
    assert ("text2sql", "sql_error") in names
    assert all(i["status"] != "completed" for i in items)  # healthy runs excluded


async def test_rca_for_a_failed_trace(client):
    items = (await client.get("/v1/apps/incidents")).json()
    sql_incident = next(i for i in items if i["root_cause"] == "sql_error")

    resp = await client.post(f"/v1/apps/incidents/{sql_incident['trace_id']}/rca")
    assert resp.status_code == 200
    rca = resp.json()
    assert rca["root_cause"] == "sql_error"
    assert rca["signals"]  # deterministic evidence even with no provider
    assert rca["summary"] == ""  # no LLM in test env


async def test_rca_unknown_trace_404(client):
    resp = await client.post("/v1/apps/incidents/nope/rca")
    assert resp.status_code == 404
