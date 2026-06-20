"""Phase 4 security hardening regression tests (from the security review)."""

import httpx
import pytest

import workbench_gateway.app as gateway_app
from workbench_gateway.app import create_app
from workbench_gateway.security import ProductionConfigError, validate_production_security
from workbench_orchestrator import Step, WorkflowDef, register
from workbench_runtime.tracing import _scrub_payload
from workbench_shared.config import Settings, get_settings


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --- Finding 6: input length caps ---


async def test_oversized_question_is_rejected(client):
    resp = await client.post("/v1/apps/text2sql/ask", json={"question": "x" * 5000})
    assert resp.status_code == 422  # pydantic max_length


async def test_oversized_agent_input_rejected(client):
    resp = await client.post("/v1/agents/demo/run", json={"input": "x" * 5000})
    assert resp.status_code == 422


# --- Finding 2: optional approval-token gate ---


async def test_approval_token_enforced_when_configured(client, monkeypatch):
    async def noop(state):
        return {}

    register(
        WorkflowDef(
            name="sec_gate",
            description="",
            steps=[Step(name="g", run=noop, requires_approval=True)],
        )
    )
    run = (await client.post("/v1/workflows/sec_gate/run", json={"input": {}})).json()

    monkeypatch.setenv("WB_APPROVAL_TOKEN", "s3cret")
    get_settings.cache_clear()
    try:
        # missing token → 401
        bad = await client.post(f"/v1/workflows/runs/{run['id']}/approve", json={"actor": "x"})
        assert bad.status_code == 401
        # correct token → allowed
        ok = await client.post(
            f"/v1/workflows/runs/{run['id']}/approve",
            json={"actor": "x"},
            headers={"X-Approval-Token": "s3cret"},
        )
        assert ok.status_code == 200
        assert ok.json()["status"] == "completed"
    finally:
        get_settings.cache_clear()


async def test_approval_open_when_token_unset(client):
    async def noop(state):
        return {}

    register(
        WorkflowDef(
            name="sec_open",
            description="",
            steps=[Step(name="g", run=noop, requires_approval=True)],
        )
    )
    run = (await client.post("/v1/workflows/sec_open/run", json={"input": {}})).json()
    resp = await client.post(f"/v1/workflows/runs/{run['id']}/approve", json={"actor": "x"})
    assert resp.status_code == 200  # no token configured → open (local demo)


# --- HIGH-2 / MED-1: production fail-fast on missing security config ---


def _prod_settings(**overrides) -> Settings:
    # Build prod Settings without the repo .env leaking real keys in (shared file).
    base = dict(env="prod", api_key="", approval_token="", cors_origins=["*"])
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_prod_without_api_key_refuses_to_start():
    with pytest.raises(ProductionConfigError, match="WB_API_KEY"):
        validate_production_security(_prod_settings(approval_token="t", cors_origins=["https://x"]))


def test_prod_without_approval_token_refuses_to_start():
    with pytest.raises(ProductionConfigError, match="WB_APPROVAL_TOKEN"):
        validate_production_security(_prod_settings(api_key="k", cors_origins=["https://x"]))


def test_prod_with_wildcard_cors_refuses_to_start():
    with pytest.raises(ProductionConfigError, match="WB_CORS_ORIGINS"):
        validate_production_security(_prod_settings(api_key="k", approval_token="t"))


def test_prod_create_app_raises_when_unconfigured(monkeypatch):
    monkeypatch.setattr(gateway_app, "get_settings", lambda: _prod_settings())
    with pytest.raises(ProductionConfigError):
        create_app()


def test_prod_fully_configured_boots(monkeypatch):
    settings = _prod_settings(api_key="k", approval_token="t", cors_origins=["https://app"])
    monkeypatch.setattr(gateway_app, "get_settings", lambda: settings)
    assert create_app() is not None  # no exception → boots


def test_dev_default_does_not_require_security_config():
    # Regression: dev stays open even with everything empty.
    validate_production_security(Settings(_env_file=None, env="dev"))
    validate_production_security(Settings(_env_file=None, env="test"))


# --- LOW-2: security headers on every response ---


async def test_security_headers_present_on_any_endpoint(client):
    for path in ("/healthz", "/v1/agents"):
        resp = await client.get(path)
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["Referrer-Policy"] == "no-referrer"


# --- Finding 4: trace payload scrubs raw DB rows ---


def test_scrub_payload_redacts_rows():
    payload = {
        "steps": [
            {
                "tool_executions": [
                    {
                        "name": "run_sql",
                        "result": '{"sql": "SELECT * FROM customers", "columns": ["id"], '
                        '"rows": [[1], [2], [3]], "row_count": 3}',
                    }
                ]
            }
        ]
    }
    scrubbed = _scrub_payload(payload)
    import json

    result = json.loads(scrubbed["steps"][0]["tool_executions"][0]["result"])
    assert result["rows"] == "[redacted: 3 rows]"
    assert result["columns"] == ["id"]  # structure preserved
    assert result["row_count"] == 3
