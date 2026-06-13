"""Map a WorkflowRun to a trace row (Sprint 5). Best-effort; never raises.

record_trace skips non-terminal runs (awaiting_approval), so a paused workflow
is recorded once it reaches a terminal state on resume.
"""

from workbench_observability import safe_record
from workbench_orchestrator.types import WorkflowRun


async def record_workflow_run(run: WorkflowRun) -> None:
    latency = sum(a.latency_ms for a in run.attempts)
    await safe_record(
        kind="workflow",
        name=run.workflow,
        status=run.status,
        latency_ms=latency,
        cost_usd=None,  # workflow steps don't aggregate model cost in v0
        num_steps=run.steps_executed,
        error=run.error,
        payload=run.model_dump(),
    )
