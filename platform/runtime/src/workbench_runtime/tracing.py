"""Map an AgentRun to a trace row (Sprint 5). Best-effort; never raises.

The trace store has no access control of its own (ADR-006 / Finding 4), so the
payload must not duplicate sensitive query data. Tool results that carry raw DB
rows (the run_sql tool) are scrubbed to keep the trace useful (sql, columns,
row_count) without persisting the row contents.
"""

import json

from workbench_observability import safe_record
from workbench_runtime.types import AgentRun


def _scrub_payload(payload: dict) -> dict:
    """Redact raw `rows` from tool-result JSON in the serialized run."""
    for step in payload.get("steps", []):
        for execution in step.get("tool_executions", []):
            result = execution.get("result")
            if not isinstance(result, str):
                continue
            try:
                parsed = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(parsed, dict) and "rows" in parsed:
                n = len(parsed["rows"]) if isinstance(parsed["rows"], list) else 0
                parsed["rows"] = f"[redacted: {n} rows]"
                execution["result"] = json.dumps(parsed, ensure_ascii=False)
    return payload


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
        payload=_scrub_payload(run.model_dump()),
    )
