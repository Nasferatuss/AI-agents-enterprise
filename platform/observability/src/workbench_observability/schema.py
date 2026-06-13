"""Pydantic views over the trace store."""

from pydantic import BaseModel, ConfigDict

# Statuses considered a successful terminal run, across all run kinds.
SUCCESS_STATUSES = {"completed"}
# In-flight statuses are not recorded as traces (recorded on the terminal resume).
NON_TERMINAL_STATUSES = {"running", "awaiting_approval"}


class TraceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    name: str
    status: str
    created_at: str
    latency_ms: int
    cost_usd: float | None
    input_tokens: int
    output_tokens: int
    num_steps: int
    error: str | None


class TraceDetail(TraceSummary):
    payload: dict


class FailureBucket(BaseModel):
    kind: str
    status: str
    count: int


class TraceAggregates(BaseModel):
    total: int
    success_rate: float  # successful / total, 0..1
    total_cost_usd: float
    p95_latency_ms: int
    by_kind: dict[str, int]
    failures: list[FailureBucket]  # failure taxonomy: non-success runs by (kind, status)
