"""Workflow registry and in-memory run store (v0; Postgres with Sprint 5)."""

from collections import OrderedDict

from workbench_orchestrator.engine import WorkflowDef, execute
from workbench_orchestrator.types import WorkflowRun

_MAX_STORED_RUNS = 200

WORKFLOWS: dict[str, WorkflowDef] = {}
_RUNS: OrderedDict[str, WorkflowRun] = OrderedDict()


def register(workflow: WorkflowDef) -> WorkflowDef:
    WORKFLOWS[workflow.name] = workflow
    return workflow


async def run_workflow(name: str, input_state: dict) -> WorkflowRun:
    run = await execute(WORKFLOWS[name], input_state)
    _RUNS[run.id] = run
    while len(_RUNS) > _MAX_STORED_RUNS:
        _RUNS.popitem(last=False)
    return run


def get_run(run_id: str) -> WorkflowRun | None:
    return _RUNS.get(run_id)


def list_runs() -> list[WorkflowRun]:
    return list(reversed(_RUNS.values()))
