"""Pydantic views over the trace store."""

from pydantic import BaseModel, ConfigDict

# Statuses considered a successful terminal run, across all run kinds.
SUCCESS_STATUSES = {"completed"}
# In-flight statuses are not recorded as traces (recorded on the terminal resume).
# NOTE: distinct from runs.NON_TERMINAL_RUN_STATUSES ({"pending","running"}), which
# drives durable-run reconcile. This set is about TRACE recording (a completed audit
# record) and so includes "awaiting_approval" but not "pending" — different concern.
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


class RunRecord(BaseModel):
    """A durable run row (live state of a long-lived run), distinct from a Trace."""

    model_config = ConfigDict(from_attributes=True)

    run_id: str
    kind: str
    status: str
    payload: dict
    idempotency_key: str | None = None
    error: str | None = None
    created_at: str
    updated_at: str


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
