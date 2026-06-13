import pytest

from workbench_orchestrator.engine import MAX_STEPS_PER_RUN, Step, WorkflowDef, execute


def _step(name: str, fn, **kw) -> Step:
    return Step(name=name, run=fn, **kw)


async def test_linear_workflow_completes_and_merges_state():
    async def a(state):
        return {"a": 1}

    async def b(state):
        return {"b": state["a"] + 1}

    wf = WorkflowDef(name="lin", description="", steps=[_step("a", a, next="b"), _step("b", b)])
    run = await execute(wf, {"seed": True})

    assert run.status == "completed"
    assert run.state == {"seed": True, "a": 1, "b": 2}
    assert [(at.step, at.status) for at in run.attempts] == [
        ("a", "succeeded"),
        ("b", "succeeded"),
    ]


async def test_retry_succeeds_on_second_attempt():
    calls = {"n": 0}

    async def flaky(state):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return {"ok": True}

    wf = WorkflowDef(name="r", description="", steps=[_step("flaky", flaky, max_attempts=3)])
    run = await execute(wf, {})

    assert run.status == "completed"
    assert [at.status for at in run.attempts] == ["retried", "succeeded"]
    assert run.attempts[0].error and "transient" in run.attempts[0].error


async def test_failure_after_max_attempts():
    async def broken(state):
        raise ValueError("nope")

    wf = WorkflowDef(
        name="f",
        description="",
        steps=[_step("broken", broken, max_attempts=2, next="after"), _step("after", broken)],
    )
    run = await execute(wf, {})

    assert run.status == "failed"
    assert "broken" in run.error
    assert len(run.attempts) == 2  # the 'after' step never ran
    assert run.attempts[-1].status == "failed"


async def test_branching_picks_route_from_state():
    async def start(state):
        return {}

    async def left(state):
        return {"route": "left"}

    async def right(state):
        return {"route": "right"}

    wf = WorkflowDef(
        name="br",
        description="",
        steps=[
            _step("start", start, next=lambda s: "left" if s.get("go") == "left" else "right"),
            _step("left", left),
            _step("right", right),
        ],
    )
    assert (await execute(wf, {"go": "left"})).state["route"] == "left"
    assert (await execute(wf, {"go": "elsewhere"})).state["route"] == "right"


async def test_step_budget_guards_against_cycles():
    async def loop(state):
        return {}

    wf = WorkflowDef(name="cycle", description="", steps=[_step("loop", loop, next="loop")])
    run = await execute(wf, {})

    assert run.status == "failed"
    assert "budget" in run.error
    assert run.steps_executed == MAX_STEPS_PER_RUN


def test_workflow_def_validates_transitions():
    async def a(state):
        return {}

    with pytest.raises(ValueError, match="unknown"):
        WorkflowDef(name="bad", description="", steps=[Step(name="a", run=a, next="ghost")])
    with pytest.raises(ValueError, match="duplicate"):
        WorkflowDef(
            name="dup", description="", steps=[Step(name="a", run=a), Step(name="a", run=a)]
        )
    with pytest.raises(ValueError, match="no steps"):
        WorkflowDef(name="empty", description="", steps=[])
