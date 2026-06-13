"""Deterministic root-cause classification from a trace.

Rule-based over (kind, status, error, payload) — a defensible category and
evidence, before any LLM narrative. The taxonomy covers the failure modes the
platform actually produces: rejected approvals, step-budget loops, provider
outages, SQL errors, denied tool calls, QA scenario failures, weak eval scores.
"""

from typing import Literal

RootCause = Literal[
    "policy_rejection",
    "loop_no_progress",
    "provider_unavailable",
    "sql_error",
    "tool_denied",
    "scenario_failures",
    "low_eval_quality",
    "unknown",
]


def classify(
    kind: str, status: str, error: str | None, payload: dict | None = None
) -> tuple[RootCause, list[str]]:
    err = (error or "").lower()
    payload = payload or {}
    signals: list[str] = []

    if status == "rejected":
        return "policy_rejection", ["workflow run rejected by a human at an approval gate"]
    if status == "max_steps_reached" or "max_steps" in err:
        steps = payload.get("steps")
        n = len(steps) if isinstance(steps, list) else payload.get("num_steps", "?")
        return "loop_no_progress", [f"agent hit the step budget without finishing ({n} steps)"]
    if "no provider" in err:
        return "provider_unavailable", [
            "no model provider succeeded — check API keys or the local model endpoint"
        ]
    if "execution failed" in err or "sql" in err:
        return "sql_error", ["a SQL query failed during execution"]
    if kind == "agent" and "scenario" in err:
        return "scenario_failures", [error or "QA scenarios failed"]

    audit = payload.get("tool_calls") or payload.get("action_trace") or []
    denied = [a for a in audit if isinstance(a, dict) and a.get("allowed") is False]
    if denied:
        signals.append(f"{len(denied)} tool call(s) denied by the gateway allowlist")
        return "tool_denied", signals

    aggregates = payload.get("aggregates")
    if kind == "eval" and isinstance(aggregates, dict):
        hit = aggregates.get("hit_rate")
        if isinstance(hit, int | float) and hit < 0.5:
            return "low_eval_quality", [f"retrieval hit rate is low ({hit:.0%})"]

    return "unknown", signals or [f"run ended with status '{status}'"]
