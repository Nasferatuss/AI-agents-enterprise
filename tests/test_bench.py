"""Network-free smoke test for the cost-aware routing benchmark harness.

Runs the harness in stub mode and asserts the aggregates are well-formed: totals
are non-negative, shares/rates live in [0,1], every case is accounted for, the
fallback path is actually exercised, and the markdown table renders.
"""

import sys
from pathlib import Path

import pytest

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


async def test_stub_savings_are_reproducible():
    # The stub is fully deterministic, so its local-first savings are a fixed,
    # offline-reproducible number (the live run reports ~33% on real providers).
    # This pins it as a regression gate: a routing/pricing change that moves the
    # headline savings fails here instead of silently shifting the published figure.
    report = await _run()
    assert report.savings_pct == pytest.approx(0.44, abs=0.02)


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


# --- Load / throughput benchmark ----------------------------------------------


async def _run_load(concurrency: int, requests: int = 32) -> bench.LoadReport:
    router = bench.build_load_stub_router()
    cases = bench.expand_cases(bench.CASES, requests)
    report = await bench.run_load_benchmark(router, cases, concurrency)
    report.mode = "stub"
    await router.aclose()
    return report


async def test_load_report_is_well_formed():
    report = await _run_load(concurrency=8)

    # Both phases ran the full expanded workload with no errors.
    assert report.requests == 32
    assert report.serial.requests == 32
    assert report.concurrent.requests == 32
    assert report.serial.errors == 0
    assert report.concurrent.errors == 0

    # Throughput is a positive req/s for both phases.
    assert report.serial.throughput_rps > 0
    assert report.concurrent.throughput_rps > 0

    # Latency percentiles are computed and ordered for both phases.
    for phase in (report.serial, report.concurrent):
        assert phase.latency.count == 32
        assert 0 < phase.latency.p50_ms <= phase.latency.p95_ms
        assert phase.latency.min_ms <= phase.latency.p50_ms
        assert phase.latency.p95_ms <= phase.latency.max_ms


async def test_load_is_actually_parallel():
    report = await _run_load(concurrency=8)

    # The defining property of real concurrency: wall-clock under load is well below
    # the sum of per-request latencies (which is the serial lower bound). If the
    # gather were secretly serial, wall-clock would ~equal that sum.
    sum_latency_s = report.concurrent.sum_latency_ms / 1000.0
    assert report.concurrent.wall_clock_s < sum_latency_s

    # And concurrent wall-clock beats the sequential phase outright.
    assert report.concurrent.wall_clock_s < report.serial.wall_clock_s
    assert report.speedup > 1.0
    # With 8-way concurrency on a quick stub we expect a substantial speedup.
    assert report.speedup >= 2.0

    # Higher concurrency must lift throughput over the sequential baseline.
    assert report.concurrent.throughput_rps > report.serial.throughput_rps


async def test_load_concurrency_one_is_serial_baseline():
    report = await _run_load(concurrency=1)

    # concurrency=1 reuses the serial phase as the concurrent phase: no speedup.
    assert report.concurrent is report.serial
    assert report.speedup == 1.0


def test_load_report_to_dict_is_json_serializable():
    import asyncio
    import json

    report = asyncio.run(_run_load(concurrency=4))
    payload = bench.load_report_to_dict(report)
    json.dumps(payload)  # must not raise
    assert payload["concurrency"] == 4
    assert payload["serial"]["latency"]["p95_ms"] >= payload["serial"]["latency"]["p50_ms"]


def test_load_markdown_renders():
    import asyncio

    report = asyncio.run(_run_load(concurrency=4))
    md = bench.render_load_markdown(report)
    assert "Load run (stub mode)" in md
    assert "throughput (req/s)" in md
    assert "speedup" in md


def test_expand_cases_preserves_mix_and_count():
    expanded = bench.expand_cases(bench.CASES, 40)
    assert len(expanded) == 40
    # Ids stay unique so each replica is addressable.
    assert len({c.id for c in expanded}) == 40
    # Complexity distribution is preserved proportionally (tiling).
    assert all(isinstance(c, bench.BenchCase) for c in expanded)
