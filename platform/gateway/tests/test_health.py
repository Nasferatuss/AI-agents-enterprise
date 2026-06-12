import httpx
import pytest

from workbench_gateway.app import create_app


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_healthz_ok(client: httpx.AsyncClient):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "gateway"
    assert body["status"] == "ok"
    assert body["dependencies"] == []


async def test_cors_allows_demo_console(client: httpx.AsyncClient):
    resp = await client.get("/healthz", headers={"Origin": "http://localhost:3000"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


async def test_healthz_deps_reports_all_dependencies(client: httpx.AsyncClient):
    resp = await client.get("/healthz/deps")
    assert resp.status_code == 200
    body = resp.json()
    names = {d["name"] for d in body["dependencies"]}
    assert names == {"postgres", "redis", "qdrant"}
    # Stack may or may not be running locally; states must be well-formed either way.
    assert all(d["state"] in {"ok", "unreachable"} for d in body["dependencies"])
    assert body["status"] in {"ok", "degraded"}
