"""Durable run store: a paused run survives a 'restart', and idempotency dedupes.

These exercise the registry against a real (in-memory) trace DB, so they cover the
persistence path the gateway uses, not just the in-process engine.
"""

import pytest

from workbench_observability import init_db, reset_engine
from workbench_orchestrator import registry
from workbench_orchestrator.engine import Step, WorkflowDef


@pytest.fixture
async def trace_db(monkeypatch):
    """Fresh in-memory trace store + clean run cache per test."""
    monkeypatch.setenv("WB_TRACE_DB_URL", "sqlite+aiosqlite:///:memory:")
    reset_engine()
    await init_db()
    registry._RUNS.clear()
    yield
    reset_engine()
    registry._RUNS.clear()


def _gated_wf(ran: dict) -> WorkflowDef:
    async def assess(state):
        return {"risk": "low"}

    async def grant(state):
        ran["granted"] = True
        return {"granted": True}

    return WorkflowDef(
        name="durable_gate",
        description="",
        steps=[
            Step(name="assess", run=assess, next="grant"),
            Step(name="grant", run=grant, next=None, requires_approval=True, approval_prompt="ok?"),
        ],
    )


async def test_paused_run_survives_restart_and_resumes(trace_db):
    ran = {"granted": False}
    registry.register(_gated_wf(ran))

    run = await registry.run_workflow("durable_gate", {})
    assert run.status == "awaiting_approval"

    # Simulate a gateway restart: the in-memory cache is gone, only the DB remains.
    registry._RUNS.clear()
    assert run.id not in registry._RUNS

    rehydrated = await registry.get_run(run.id)
    assert rehydrated is not None
    assert rehydrated.status == "awaiting_approval"
    assert rehydrated.pending_step == "grant"

    # Approving after the 'restart' must still work and execute the gate.
    resumed = await registry.resume_run(run.id, decision="approved", actor="alice")
    assert resumed.status == "completed"
    assert ran["granted"] is True
    assert resumed.approvals[0].actor == "alice"


async def test_idempotency_key_dedupes_runs(trace_db):
    calls = {"n": 0}

    async def step(state):
        calls["n"] += 1
        return {"n": calls["n"]}

    registry.register(WorkflowDef(name="idem_wf", description="", steps=[Step(name="s", run=step)]))

    r1 = await registry.run_workflow("idem_wf", {}, idempotency_key="abc")
    r2 = await registry.run_workflow("idem_wf", {}, idempotency_key="abc")
    assert r1.id == r2.id  # same run returned, not a second one
    assert calls["n"] == 1  # the costly work ran exactly once

    r3 = await registry.run_workflow("idem_wf", {}, idempotency_key="xyz")
    assert r3.id != r1.id  # a different key is a different run
    assert calls["n"] == 2
