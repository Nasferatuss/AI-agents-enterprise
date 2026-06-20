import pytest

from workbench_observability import aggregates, get_trace, list_traces, record_trace
from workbench_observability.schema import FailureBucket
from workbench_observability.store import safe_record


async def _seed():
    await record_trace(
        kind="agent",
        name="demo",
        status="completed",
        latency_ms=120,
        cost_usd=0.002,
        input_tokens=100,
        output_tokens=50,
        num_steps=2,
        error=None,
        payload={"a": 1},
    )
    await record_trace(
        kind="workflow",
        name="content_brief",
        status="failed",
        latency_ms=300,
        cost_usd=None,
        num_steps=3,
        error="boom",
        payload={"b": 2},
    )
    await record_trace(
        kind="eval",
        name="ds",
        status="completed",
        latency_ms=0,
        cost_usd=0.05,
        num_steps=5,
        error=None,
        payload={"c": 3},
    )


async def test_record_and_list_newest_first(trace_db):
    await _seed()
    traces = await list_traces()
    assert len(traces) == 3
    assert [t.kind for t in traces] == ["eval", "workflow", "agent"]  # newest first


async def test_filter_by_kind(trace_db):
    await _seed()
    agents = await list_traces(kind="agent")
    assert len(agents) == 1 and agents[0].name == "demo"


async def test_get_trace_detail_has_payload(trace_db):
    tid = await record_trace(
        kind="agent", name="x", status="completed", payload={"steps": [1, 2, 3]}
    )
    detail = await get_trace(tid)
    assert detail is not None
    assert detail.payload == {"steps": [1, 2, 3]}
    assert await get_trace("missing") is None


async def test_non_terminal_run_is_not_recorded(trace_db):
    tid = await record_trace(kind="workflow", name="w", status="awaiting_approval", payload={})
    assert tid is None
    assert await list_traces() == []


async def test_aggregates_and_failure_taxonomy(trace_db):
    await _seed()
    agg = await aggregates()
    assert agg.total == 3
    assert agg.success_rate == pytest.approx(2 / 3)  # 2 completed of 3
    assert agg.total_cost_usd == pytest.approx(0.052)
    assert agg.by_kind == {"agent": 1, "workflow": 1, "eval": 1}
    assert agg.failures == [type(agg.failures[0])(kind="workflow", status="failed", count=1)]


async def test_aggregates_sql_refactor_regression(trace_db):
    # Mixed kinds, statuses and latencies — verifies the SQL-pushed-down counts,
    # cost sum, by_kind grouping, failure taxonomy ordering, and sqlite p95 fallback.
    latencies = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    for i, lat in enumerate(latencies):
        await record_trace(
            kind="agent",
            name=f"a{i}",
            status="completed",
            latency_ms=lat,
            cost_usd=0.001,
            payload={},
        )
    # two failure buckets, with workflow/failed appearing twice (most common first)
    await record_trace(kind="workflow", name="w1", status="failed", error="x", payload={})
    await record_trace(kind="workflow", name="w2", status="failed", error="y", payload={})
    await record_trace(kind="eval", name="e1", status="error", error="z", payload={})

    agg = await aggregates()
    assert agg.total == 13
    assert agg.success_rate == pytest.approx(10 / 13)
    assert agg.total_cost_usd == pytest.approx(0.01)  # 10 * 0.001
    assert agg.by_kind == {"agent": 10, "workflow": 2, "eval": 1}
    # sqlite p95 fallback: index = min(9, int(10 * 0.95)) over 10 agent + 3 zero latencies
    # 13 latencies sorted: 0,0,0,10,20,...,100 ; idx = int(13*0.95)=12 → 100
    assert agg.p95_latency_ms == 100
    assert agg.failures[0] == FailureBucket(kind="workflow", status="failed", count=2)
    assert FailureBucket(kind="eval", status="error", count=1) in agg.failures


async def test_record_tool_audit_persists_denied_and_allowed(trace_db):
    from workbench_observability.store import record_tool_audit

    await record_tool_audit(
        {"tool": "web_search", "args": {"q": "x"}, "allowed": True, "latency_ms": 5, "at": "t"}
    )
    await record_tool_audit(
        {"tool": "danger", "args": {}, "allowed": False, "error": "denied", "at": "t"}
    )

    traces = await list_traces(kind="tool")
    by_name = {t.name: t for t in traces}
    assert by_name["web_search"].status == "completed"
    assert by_name["danger"].status == "denied"
    assert by_name["danger"].error == "denied"


async def test_safe_record_swallows_errors(trace_db, monkeypatch):
    # payload that cannot serialize to JSON column → record_trace raises → safe_record swallows
    import workbench_observability.store as store

    async def boom(**kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(store, "record_trace", boom)
    assert await safe_record(kind="agent", name="x", status="completed", payload={}) is None
