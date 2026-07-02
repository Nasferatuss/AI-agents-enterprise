"""Optional API auth + rate limiting (Phase 5 hardening)."""

import httpx
import pytest

from workbench_gateway.app import create_app
from workbench_shared.config import get_settings


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=create_app(), client=("1.2.3.4", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_default_is_open(client):
    # no WB_API_KEY / WB_RATE_LIMIT_PER_MIN → everything works (the demo default)
    assert (await client.get("/v1/agents")).status_code == 200
    assert (await client.get("/healthz")).status_code == 200


async def test_api_key_required_when_set(monkeypatch):
    monkeypatch.setenv("WB_API_KEY", "topsecret")
    get_settings.cache_clear()
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        # health stays open (not under /v1)
        assert (await c.get("/healthz")).status_code == 200
        # /v1 without the key → 401
        assert (await c.get("/v1/agents")).status_code == 401
        # with the right key → 200
        ok = await c.get("/v1/agents", headers={"X-API-Key": "topsecret"})
        assert ok.status_code == 200
    get_settings.cache_clear()


async def test_rate_limit_when_set(monkeypatch):
    monkeypatch.setenv("WB_RATE_LIMIT_PER_MIN", "2")
    get_settings.cache_clear()
    transport = httpx.ASGITransport(app=create_app(), client=("9.9.9.9", 1))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        body = {"document": "Stores SSN 123-45-6789."}  # deterministic, no provider
        assert (await c.post("/v1/apps/compliance/review", json=body)).status_code == 200
        # a GET counts toward the SAME per-IP window (reads are as abusable as writes)
        assert (await c.get("/v1/agents")).status_code == 200
        # third /v1 request within the window → 429, regardless of method
        assert (await c.post("/v1/apps/compliance/review", json=body)).status_code == 429
        assert (await c.get("/v1/agents")).status_code == 429
        # non-/v1 (health) is never limited
        assert (await c.get("/healthz")).status_code == 200
    get_settings.cache_clear()
