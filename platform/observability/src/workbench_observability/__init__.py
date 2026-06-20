"""Observability Layer: custom trace schema, recording, and queries (ADR-006)."""

from workbench_observability.db import init_db, reset_engine
from workbench_observability.runs import (
    create_run,
    get_run,
    get_run_by_idempotency_key,
    list_nonterminal_runs,
    list_runs,
    upsert_run,
)
from workbench_observability.schema import (
    RunRecord,
    TraceAggregates,
    TraceDetail,
    TraceSummary,
)
from workbench_observability.store import (
    aggregates,
    get_trace,
    list_traces,
    record_tool_audit,
    record_trace,
    safe_record,
)

__all__ = [
    "RunRecord",
    "TraceAggregates",
    "TraceDetail",
    "TraceSummary",
    "aggregates",
    "create_run",
    "get_run",
    "get_run_by_idempotency_key",
    "get_trace",
    "init_db",
    "list_nonterminal_runs",
    "list_runs",
    "list_traces",
    "record_tool_audit",
    "record_trace",
    "reset_engine",
    "safe_record",
    "upsert_run",
]
