"""Workflow registry + durable run store.

Runs are persisted to the trace DB (`workbench_observability.runs`) so a
human-in-the-loop gate survives a gateway restart — a run can sit
`awaiting_approval` for hours, and resuming it must not depend on the process
that created it still being alive. The in-memory `OrderedDict` is a fast
write-through cache; on a miss (after a restart, or on another replica) the run
is rehydrated from the DB. Persistence is best-effort: if the store is down the
engine still works in-memory exactly as before (durability is a mirror, not the
critical path). `run_workflow` honors an idempotency key so a client/LB retry
returns the original run instead of launching a second costly one.
"""

from collections import OrderedDict

from workbench_observability import get_run as _db_get_run
from workbench_observability import (
    get_run_by_idempotency_key,
    upsert_run,
)
from workbench_observability import list_runs as _db_list_runs
from workbench_orchestrator.engine import WorkflowDef, execute, resume
from workbench_orchestrator.types import ApprovalDecision, WorkflowRun

_KIND = "workflow"
_MAX_STORED_RUNS = 200

WORKFLOWS: dict[str, WorkflowDef] = {}
_RUNS: OrderedDict[str, WorkflowRun] = OrderedDict()


def register(workflow: WorkflowDef) -> WorkflowDef:
    WORKFLOWS[workflow.name] = workflow
    return workflow


async def _store(run: WorkflowRun, idempotency_key: str | None = None) -> WorkflowRun:
    _RUNS[run.id] = run
    while len(_RUNS) > _MAX_STORED_RUNS:
        _RUNS.popitem(last=False)
    await upsert_run(
        run_id=run.id,
        kind=_KIND,
        status=run.status,
        payload=run.model_dump(),
        idempotency_key=idempotency_key,
    )
    return run


async def _load(run_id: str) -> WorkflowRun | None:
    """In-memory first, then rehydrate from the durable store (post-restart)."""
    if run_id in _RUNS:
        return _RUNS[run_id]
    record = await _db_get_run(run_id)
    if record is None:
        return None
    run = WorkflowRun.model_validate(record.payload)
    _RUNS[run.id] = run  # warm the cache
    return run


async def run_workflow(
    name: str, input_state: dict, *, idempotency_key: str | None = None
) -> WorkflowRun:
    # Idempotency: a repeated key returns the original run, never a second one.
    if idempotency_key:
        existing = await get_run_by_idempotency_key(_KIND, idempotency_key)
        if existing is not None:
            run = WorkflowRun.model_validate(existing.payload)
            _RUNS[run.id] = run
            return run
    return await _store(await execute(WORKFLOWS[name], input_state), idempotency_key)


async def resume_run(
    run_id: str, *, decision: ApprovalDecision, actor: str, reason: str | None = None
) -> WorkflowRun:
    """Resume a paused run with an approval decision. Raises KeyError if unknown."""
    run = await _load(run_id)
    if run is None:
        raise KeyError(run_id)
    resumed = await resume(
        WORKFLOWS[run.workflow], run, decision=decision, actor=actor, reason=reason
    )
    return await _store(resumed)


async def get_run(run_id: str) -> WorkflowRun | None:
    return await _load(run_id)


async def list_runs() -> list[WorkflowRun]:
    """Most-recent-first runs from the durable store, falling back to memory."""
    records = await _db_list_runs(_KIND, limit=_MAX_STORED_RUNS)
    if records:
        return [WorkflowRun.model_validate(r.payload) for r in records]
    return list(reversed(_RUNS.values()))
