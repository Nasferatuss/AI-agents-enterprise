"""Phase 4 security hardening regression tests (from the security review)."""

import httpx
import pytest

from workbench_gateway.app import create_app
from workbench_orchestrator import Step, WorkflowDef, register
from workbench_runtime.tracing import _scrub_payload
from workbench_shared.config import get_settings


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
