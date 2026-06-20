"""Network-free smoke test for the cost-aware routing benchmark harness.

Runs the harness in stub mode and asserts the aggregates are well-formed: totals
are non-negative, shares/rates live in [0,1], every case is accounted for, the
fallback path is actually exercised, and the markdown table renders.
"""

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import bench  # noqa: E402


async def _run() -> bench.BenchReport:
    router = bench.build_stub_router()
    report = await bench.run_benchmark(router, bench.CASES, "stub")
    bench._apply_stub_latency(report)
    await router.aclose()
    return report


async def test_stub_report_is_complete_and_well_formed():
    report = await _run()

    # Every case produced a result.
    assert report.count == len(bench.CASES)
    assert {r.id for r in report.results} == {c.id for c in bench.CASES}

    # Costs are non-negative and the mean is consistent with the total.
    assert report.total_cost_usd >= 0
    assert report.mean_cost_usd >= 0
    assert abs(report.mean_cost_usd * report.count - report.total_cost_usd) < 1e-3

    # Latency percentiles are ordered and positive.
    assert 0 < report.p50_latency_ms <= report.p95_latency_ms

    # Shares and rates are valid probabilities.
    assert 0.0 <= report.fallback_rate <= 1.0
    for share in report.tier_share.values():
        assert 0.0 <= share <= 1.0
    assert abs(sum(report.tier_share.values()) - 1.0) < 1e-6

    # Distributions sum to the request count.
    assert sum(report.provider_dist.values()) == report.count
    assert sum(report.tier_dist.values()) == report.count


async def test_stub_exercises_local_first_and_fallback():
    report = await _run()

    # Local is "down" in the stub, so simple/standard cases fall back off local
    # onto a cheap provider — fallback must be observed.
    assert report.fallback_rate > 0
    assert any(r.fallback for r in report.results)

    # Cheap tier should serve the bulk of simple/standard work; frontier only the
    # complex/judge cases. Both tiers must appear.
    assert report.tier_dist.get("cheap", 0) > 0
    assert report.tier_dist.get("frontier", 0) > 0


async def test_savings_are_positive_and_bounded():
    report = await _run()

    # Routing cheap/local work away from frontier must cost less than the
    # all-frontier baseline — that is the whole thesis.
    assert report.frontier_baseline_usd > 0
    assert report.total_cost_usd < report.frontier_baseline_usd
    assert report.savings_usd > 0
    assert 0.0 < report.savings_pct <= 1.0


async def test_markdown_renders_nonempty_table():
    report = await _run()
    md = bench.render_markdown(report)

    assert "Benchmark run (stub mode)" in md
    assert "| case | complexity | provider | tier | model |" in md
    assert "Local-first savings" in md
    # One header row + separator + one row per case at minimum.
    assert md.count("\n") > len(bench.CASES)


def test_report_to_dict_is_json_serializable():
    import json

    report = bench.BenchReport(mode="stub")
    payload = bench.report_to_dict(report)
    json.dumps(payload)  # must not raise
    assert payload["mode"] == "stub"
