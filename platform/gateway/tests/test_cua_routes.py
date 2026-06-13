import httpx
import pytest

from workbench_gateway.app import create_app


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_scenarios_listed(client):
    resp = await client.get("/v1/apps/cua/scenarios")
    names = {s["name"] for s in resp.json()}
    assert {"login_valid", "email_validation", "dashboard_copy"} <= names


async def test_initial_screen_is_the_login(client):
    screen = (await client.get("/v1/apps/cua/screen")).json()
    assert screen["state"] == "login"
    assert any(e["id"] == "submit" for e in screen["elements"])


async def test_run_produces_bug_report_without_provider(client):
    # deterministic results return even with no LLM (narrative is best-effort)
    report = (await client.post("/v1/apps/cua/run")).json()
    assert report["passed"] == 3
    assert report["failed"] == 2
    assert {b["scenario"] for b in report["bugs"]} == {"email_validation", "dashboard_copy"}
    assert len(report["action_trace"]) > 0
    assert report["summary"] == ""  # no provider in test env
