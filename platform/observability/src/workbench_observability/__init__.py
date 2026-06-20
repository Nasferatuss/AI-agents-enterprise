"""Observability Layer: custom trace schema, recording, and queries (ADR-006)."""

from workbench_observability.db import init_db, reset_engine
from workbench_observability.schema import TraceAggregates, TraceDetail, TraceSummary
from workbench_observability.store import (
    aggregates,
    get_trace,
    list_traces,
    record_tool_audit,
    record_trace,
    safe_record,
)

__all__ = [
    "TraceAggregates",
    "TraceDetail",
    "TraceSummary",
    "aggregates",
    "get_trace",
    "init_db",
    "list_traces",
    "record_tool_audit",
    "record_trace",
    "reset_engine",
    "safe_record",
]
