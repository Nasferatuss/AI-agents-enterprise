"""Map an AgentRun to a trace row (Sprint 5). Best-effort; never raises."""

from workbench_observability import safe_record
from workbench_runtime.types import AgentRun


async def record_agent_run(run: AgentRun, *, name: str | None = None) -> None:
    latency = sum(step.output.latency_ms for step in run.steps)
    await safe_record(
        kind="agent",
        name=name or run.agent,
        status=run.status,
        latency_ms=latency,
        cost_usd=run.cost_usd,
        input_tokens=run.usage.input_tokens,
        output_tokens=run.usage.output_tokens,
        num_steps=len(run.steps),
        error=None if run.status == "completed" else run.status,
        payload=run.model_dump(),
    )
