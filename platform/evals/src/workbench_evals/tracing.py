"""Map an EvalReport to a trace row (Sprint 5). Best-effort; never raises."""

from workbench_evals.types import EvalReport
from workbench_observability import safe_record


async def record_eval_report(report: EvalReport) -> None:
    await safe_record(
        kind="eval",
        name=report.dataset,
        status="completed",
        cost_usd=report.llm_cost_usd,
        num_steps=report.aggregates.n,
        error=None,
        payload=report.model_dump(),
    )
