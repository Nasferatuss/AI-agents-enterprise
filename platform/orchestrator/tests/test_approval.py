import pytest

from workbench_orchestrator.engine import ApprovalError, Step, WorkflowDef, execute, resume


def _gated_workflow() -> tuple[WorkflowDef, dict]:
    ran: dict[str, bool] = {"granted": False}

    async def assess(state):
        return {"risk": "low"}

    async def grant(state):
        ran["granted"] = True
        return {"granted": True}

    wf = WorkflowDef(
        name="gate",
        description="",
        steps=[
            Step(name="assess", run=assess, next="grant"),
            Step(
                name="grant",
                run=grant,
                next=None,
                requires_approval=True,
                approval_prompt="OK to grant?",
            ),
        ],
    )
    return wf, ran


async def test_run_suspends_at_gate_without_executing_it():
    wf, ran = _gated_workflow()
    run = await execute(wf, {})

    assert run.status == "awaiting_approval"
    assert run.pending_step == "grant"
    assert run.approval_prompt == "OK to grant?"
    assert ran["granted"] is False  # the risky step has NOT run
    assert run.state["risk"] == "low"  # but the pre-gate step did
    assert [a.step for a in run.attempts] == ["assess"]


async def test_approve_runs_the_gate_and_completes():
    wf, ran = _gated_workflow()
    run = await execute(wf, {})
    resumed = await resume(wf, run, decision="approved", actor="alice", reason="looks fine")

    assert resumed.status == "completed"
    assert ran["granted"] is True
    assert resumed.state["granted"] is True
    assert resumed.pending_step is None
    assert len(resumed.approvals) == 1
    record = resumed.approvals[0]
    assert (record.step, record.decision, record.actor, record.reason) == (
        "grant",
        "approved",
        "alice",
        "looks fine",
    )
    assert [a.step for a in resumed.attempts] == ["assess", "grant"]


async def test_reject_ends_run_without_executing_the_gate():
    wf, ran = _gated_workflow()
    run = await execute(wf, {})
    resumed = await resume(wf, run, decision="rejected", actor="bob")

    assert resumed.status == "rejected"
    assert ran["granted"] is False
    assert "rejected by bob" in resumed.error
    assert resumed.approvals[0].decision == "rejected"
    assert [a.step for a in resumed.attempts] == ["assess"]  # gate never ran


async def test_resume_on_non_awaiting_run_raises():
    wf, _ = _gated_workflow()
    run = await execute(wf, {})
    await resume(wf, run, decision="approved", actor="alice")  # now completed
    with pytest.raises(ApprovalError, match="not awaiting approval"):
        await resume(wf, run, decision="approved", actor="alice")


async def test_gate_after_branch_still_pauses():
    async def start(state):
        return {}

    async def safe(state):
        return {"path": "safe"}

    async def risky(state):
        return {"path": "risky"}

    wf = WorkflowDef(
        name="branchgate",
        description="",
        steps=[
            Step(name="start", run=start, next=lambda s: "risky" if s.get("danger") else "safe"),
            Step(name="safe", run=safe, next=None),
            Step(name="risky", run=risky, next=None, requires_approval=True),
        ],
    )
    safe_run = await execute(wf, {"danger": False})
    assert safe_run.status == "completed"  # safe path has no gate

    risky_run = await execute(wf, {"danger": True})
    assert risky_run.status == "awaiting_approval"
    assert risky_run.pending_step == "risky"
