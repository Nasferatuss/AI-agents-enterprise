"""Workflow registry and in-memory run store (v0; Postgres with Sprint 5)."""

from collections import OrderedDict

from workbench_orchestrator.engine import WorkflowDef, execute, resume
from workbench_orchestrator.types import ApprovalDecision, WorkflowRun

_MAX_STORED_RUNS = 200

WORKFLOWS: dict[str, WorkflowDef] = {}
_RUNS: OrderedDict[str, WorkflowRun] = OrderedDict()


def register(workflow: WorkflowDef) -> WorkflowDef:
    WORKFLOWS[workflow.name] = workflow
    return workflow


def _store(run: WorkflowRun) -> WorkflowRun:
    _RUNS[run.id] = run
    while len(_RUNS) > _MAX_STORED_RUNS:
        _RUNS.popitem(last=False)
    return run


async def run_workflow(name: str, input_state: dict) -> WorkflowRun:
    return _store(await execute(WORKFLOWS[name], input_state))


async def resume_run(
    run_id: str, *, decision: ApprovalDecision, actor: str, reason: str | None = None
) -> WorkflowRun:
    """Resume a paused run with an approval decision. Raises KeyError if unknown."""
    run = _RUNS[run_id]
    resumed = await resume(
        WORKFLOWS[run.workflow], run, decision=decision, actor=actor, reason=reason
    )
    return _store(resumed)


def get_run(run_id: str) -> WorkflowRun | None:
    return _RUNS.get(run_id)


def list_runs() -> list[WorkflowRun]:
    return list(reversed(_RUNS.values()))
