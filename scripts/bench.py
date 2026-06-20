"""Cost-aware routing benchmark harness (ADR-008).

Runs a fixed, representative prompt set through ``ModelRouter`` and reports the
numbers that prove local-first routing pays off under load: per-request provider/
tier/cost/latency/fallback, then aggregates — total & mean cost, p50/p95 latency,
provider & tier distribution, and the headline "local-first savings": how much the
same workload would have cost if every request had gone straight to a frontier
model.

Two modes:

* ``--stub`` (default) — a deterministic, fully network-free fake provider stack
  (httpx ``MockTransport``, same pattern as the router tests). Reproducible, safe
  for CI; the numbers are *illustrative* (baked-in tokens/latency), not measured.
* ``--live`` — the real registry from configuration (Ollama / cheap APIs /
  frontier). Goes to the network; numbers are *real*. Run it yourself.

Core logic (``run_benchmark`` / ``render_markdown``) is importable and pure so it
can be unit-tested; the CLI is a thin wrapper.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx

# Make the runtime importable when run as a plain script (uv handles this under
# `uv run`, but a direct `python scripts/bench.py` should work too).
_RUNTIME_SRC = Path(__file__).resolve().parents[1] / "platform" / "runtime" / "src"
if _RUNTIME_SRC.is_dir() and str(_RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_SRC))

from workbench_runtime.pricing import estimate_cost_usd  # noqa: E402
from workbench_runtime.providers import Provider, build_registry  # noqa: E402
from workbench_runtime.router import ModelRouter  # noqa: E402
from workbench_runtime.types import ChatMessage, Complexity  # noqa: E402

# --- Representative workload ---------------------------------------------------
# A fixed prompt set tagged with the complexity a router should pick for it. The
# mix is deliberately skewed toward simple/standard work — that is exactly the
# distribution where local-first routing earns its keep in a real product.


@dataclass(frozen=True)
class BenchCase:
    id: str
    prompt: str
    complexity: Complexity


CASES: list[BenchCase] = [
    BenchCase(
        "classify-1",
        "Classify this ticket as bug/feature/question: 'app crashes on login'.",
        "simple",
    ),  # noqa: E501
    BenchCase(
        "extract-1",
        "Extract the date and amount from: 'Invoice #42, $1,250 due 2026-07-01'.",
        "simple",
    ),  # noqa: E501
    BenchCase(
        "sentiment-1",
        "Is this review positive or negative? 'Worked fine until the update.'",
        "simple",
    ),  # noqa: E501
    BenchCase(
        "summarize-1",
        "Summarize in one sentence: a 3-paragraph release note about a caching fix.",
        "simple",
    ),  # noqa: E501
    BenchCase("translate-1", "Translate 'Where is the nearest station?' to French.", "simple"),
    BenchCase("draft-1", "Draft a two-sentence reply declining a meeting politely.", "standard"),
    BenchCase(
        "sql-1", "Write a SQL query for total revenue per customer in the last 30 days.", "standard"
    ),  # noqa: E501
    BenchCase(
        "rewrite-1", "Rewrite this paragraph to be more concise without losing meaning.", "standard"
    ),  # noqa: E501
    BenchCase("explain-1", "Explain what a database index is to a junior engineer.", "standard"),
    BenchCase("plan-1", "Outline the steps to migrate a service from REST to gRPC.", "standard"),
    BenchCase(
        "reason-1",
        "Design a rate limiter that is fair across tenants under burst load; justify trade-offs.",
        "complex",
    ),  # noqa: E501
    BenchCase(
        "synth-1",
        "Given conflicting benchmarks, decide which caching strategy to adopt and why.",
        "complex",
    ),  # noqa: E501
    BenchCase(
        "debug-1", "Diagnose a deadlock from these two stack traces and propose a fix.", "complex"
    ),  # noqa: E501
    BenchCase(
        "arch-1", "Propose an architecture for a multi-region write-heavy event store.", "complex"
    ),  # noqa: E501
    BenchCase(
        "audit-1",
        "Review this routing policy for cost/latency regressions and recommend changes.",
        "judge",
    ),  # noqa: E501
]

# Frontier baseline used for the "what if everything went frontier" counterfactual.
_FRONTIER_MODEL = "claude-opus-4-8"

_TIER_BY_PROVIDER: dict[str, str] = {
    "local": "local",
    "deepseek": "cheap",
    "kimi": "cheap",
    "mimo": "cheap",
    "anthropic": "frontier",
    "openai": "frontier",
}


def tier_for(provider: str) -> str:
    return _TIER_BY_PROVIDER.get(provider, "other")


# --- Result types --------------------------------------------------------------


@dataclass
class CaseResult:
    id: str
    complexity: str
    provider: str
    model: str
    tier: str
    cost_usd: float | None
    latency_ms: int
    fallback: bool
    attempts: list[str]
    input_tokens: int
    output_tokens: int


@dataclass
class BenchReport:
    mode: str
    results: list[CaseResult] = field(default_factory=list)

    # Aggregates (filled by run_benchmark / recompute).
    total_cost_usd: float = 0.0
    mean_cost_usd: float = 0.0
    p50_latency_ms: int = 0
    p95_latency_ms: int = 0
    provider_dist: dict[str, int] = field(default_factory=dict)
    tier_dist: dict[str, int] = field(default_factory=dict)
    tier_share: dict[str, float] = field(default_factory=dict)
    fallback_rate: float = 0.0
    frontier_baseline_usd: float = 0.0
    savings_usd: float = 0.0
    savings_pct: float = 0.0

    @property
    def count(self) -> int:
        return len(self.results)


def _percentile(sorted_vals: list[int], pct: float) -> int:
    if not sorted_vals:
        return 0
    # Nearest-rank percentile — robust for small n and avoids interpolation noise.
    rank = max(1, int(round(pct / 100.0 * len(sorted_vals))))
    return sorted_vals[min(rank, len(sorted_vals)) - 1]


def _frontier_cost(case: CaseResult) -> float:
    """What this request would have cost on the frontier baseline model.

    Uses the request's own token counts so the counterfactual is apples-to-apples.
    """
    cost = estimate_cost_usd(_FRONTIER_MODEL, case.input_tokens, case.output_tokens)
    return cost or 0.0


def _aggregate(report: BenchReport) -> BenchReport:
    results = report.results
    n = len(results)
    costs = [r.cost_usd or 0.0 for r in results]
    latencies = sorted(r.latency_ms for r in results)

    report.total_cost_usd = round(sum(costs), 6)
    report.mean_cost_usd = round(sum(costs) / n, 6) if n else 0.0
    report.p50_latency_ms = _percentile(latencies, 50)
    report.p95_latency_ms = _percentile(latencies, 95)

    provider_dist: dict[str, int] = {}
    tier_dist: dict[str, int] = {}
    for r in results:
        provider_dist[r.provider] = provider_dist.get(r.provider, 0) + 1
        tier_dist[r.tier] = tier_dist.get(r.tier, 0) + 1
    report.provider_dist = provider_dist
    report.tier_dist = tier_dist
    report.tier_share = {t: round(c / n, 4) for t, c in tier_dist.items()} if n else {}

    report.fallback_rate = round(sum(1 for r in results if r.fallback) / n, 4) if n else 0.0

    baseline = sum(_frontier_cost(r) for r in results)
    report.frontier_baseline_usd = round(baseline, 6)
    report.savings_usd = round(baseline - report.total_cost_usd, 6)
    report.savings_pct = round(report.savings_usd / baseline, 4) if baseline > 0 else 0.0
    return report


async def run_benchmark(router: ModelRouter, cases: list[BenchCase], mode: str) -> BenchReport:
    """Run every case through the router and aggregate. Pure given a router."""
    report = BenchReport(mode=mode)
    for case in cases:
        completion = await router.complete(
            [ChatMessage(role="user", content=case.prompt)],
            complexity=case.complexity,
        )
        report.results.append(
            CaseResult(
                id=case.id,
                complexity=case.complexity,
                provider=completion.provider,
                model=completion.model,
                tier=tier_for(completion.provider),
                cost_usd=completion.cost_usd,
                latency_ms=completion.latency_ms,
                fallback=bool(completion.attempts),
                attempts=completion.attempts,
                input_tokens=completion.usage.input_tokens,
                output_tokens=completion.usage.output_tokens,
            )
        )
    return _aggregate(report)


# --- Stub provider stack (network-free, deterministic) -------------------------
# Every candidate is an OpenAI-compatible provider backed by an httpx MockTransport
# so no real network/SDK is touched. Models map onto real pricing-table ids so the
# cost arithmetic is exactly the production code path. Tokens/latency are baked in
# per provider to make a stable, illustrative profile; the "local" host fails on
# one tier to exercise the fallback accounting end-to-end.

_STUB_PROFILE: dict[str, dict] = {
    # host → response shape: model id, token usage, simulated server-side latency.
    "local": {"model": "qwen2.5:14b-instruct", "in": 220, "out": 90},
    "deepseek": {"model": "deepseek-chat", "in": 240, "out": 160},
    "kimi": {"model": "kimi-k2-0905-preview", "in": 240, "out": 160},
    "anthropic": {"model": "claude-opus-4-8", "in": 300, "out": 420},
    "openai": {"model": "gpt-5.1", "in": 300, "out": 420},
}

# Baked per-provider latency (ms) reported by the router via wall-clock; we can't
# truly slow MockTransport without real sleeps, so the harness injects these into
# the report after the run for a realistic, deterministic latency profile.
_STUB_LATENCY_MS: dict[str, int] = {
    "local": 180,
    "deepseek": 640,
    "kimi": 700,
    "anthropic": 1900,
    "openai": 1750,
}

# Hosts that are "down" in the stub, to exercise fallback bookkeeping.
_STUB_DOWN_HOSTS: set[str] = {"local"}


def _stub_provider(name: str) -> Provider:
    return Provider(
        name=name,
        kind="openai_compatible",
        base_url=f"http://{name}.stub/v1",
        api_key_env="",  # treated as always-enabled, no key required
        models={"default": _STUB_PROFILE[name]["model"], "small": "claude-haiku-4-5"},
    )


def _stub_handler(request: httpx.Request) -> httpx.Response:
    host = request.url.host.split(".")[0]
    if host in _STUB_DOWN_HOSTS:
        return httpx.Response(503, text="stub: host down")
    profile = _STUB_PROFILE.get(host, {"in": 200, "out": 100})
    body = json.loads(request.content or b"{}")
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": f"[stub:{host}] ok"}}],
            "usage": {
                "prompt_tokens": profile["in"],
                "completion_tokens": profile["out"],
                "model": body.get("model", ""),
            },
        },
    )


class _StubRouter(ModelRouter):
    """Router whose chain mirrors the real local→cheap→frontier tiers but resolves
    against the stub registry, so the production fallback logic runs unchanged."""

    def chain(self, complexity: Complexity):  # type: ignore[override]
        local = [("local", "default")]
        cheap = [("deepseek", "default"), ("kimi", "default")]
        frontier = [("anthropic", "default"), ("openai", "default")]
        match complexity:
            case "simple":
                chain = local + cheap + [("anthropic", "small")]
            case "standard":
                chain = local + cheap + frontier
            case _:  # complex | judge
                chain = frontier
        return [(p, r) for p, r in chain if p in self.registry and self.registry[p].enabled]


def build_stub_router() -> ModelRouter:
    registry = {name: _stub_provider(name) for name in _STUB_PROFILE}
    http = httpx.AsyncClient(transport=httpx.MockTransport(_stub_handler))
    router = _StubRouter(registry=registry, http=http)
    return router


def _apply_stub_latency(report: BenchReport) -> None:
    """Overlay deterministic per-provider latency onto a stub run (MockTransport
    is ~0ms wall-clock). Recompute the latency aggregates afterwards."""
    for r in report.results:
        r.latency_ms = _STUB_LATENCY_MS.get(r.provider, r.latency_ms or 100)
    _aggregate(report)


def build_live_router() -> ModelRouter:
    return ModelRouter(registry=build_registry())


# --- Rendering -----------------------------------------------------------------


def _fmt_cost(v: float | None) -> str:
    return "—" if v is None else f"${v:.6f}"


def render_markdown(report: BenchReport) -> str:
    lines: list[str] = []
    lines.append(f"### Benchmark run ({report.mode} mode) — {report.count} requests")
    lines.append("")

    # Per-request table.
    lines.append("| case | complexity | provider | tier | model | cost | latency_ms | fallback |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in report.results:
        fb = "yes" if r.fallback else ""
        lines.append(
            f"| {r.id} | {r.complexity} | {r.provider} | {r.tier} | {r.model} | "
            f"{_fmt_cost(r.cost_usd)} | {r.latency_ms} | {fb} |"
        )
    lines.append("")

    # Aggregates.
    lines.append("#### Aggregates")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append(f"| total cost | {_fmt_cost(report.total_cost_usd)} |")
    lines.append(f"| mean cost / request | {_fmt_cost(report.mean_cost_usd)} |")
    lines.append(f"| p50 latency | {report.p50_latency_ms} ms |")
    lines.append(f"| p95 latency | {report.p95_latency_ms} ms |")
    lines.append(f"| fallback rate | {report.fallback_rate:.0%} |")
    tier_share = ", ".join(
        f"{t} {report.tier_share.get(t, 0.0):.0%}" for t in ("local", "cheap", "frontier")
    )
    lines.append(f"| tier share | {tier_share} |")
    prov = ", ".join(f"{p} {c}" for p, c in sorted(report.provider_dist.items()))
    lines.append(f"| provider distribution | {prov} |")
    lines.append("")

    # Savings headline.
    lines.append("#### Local-first savings vs all-frontier baseline")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append(f"| actual cost | {_fmt_cost(report.total_cost_usd)} |")
    lines.append(
        f"| baseline (all `{_FRONTIER_MODEL}`) | {_fmt_cost(report.frontier_baseline_usd)} |"
    )
    lines.append(f"| saved | {_fmt_cost(report.savings_usd)} ({report.savings_pct:.0%}) |")
    return "\n".join(lines)


def report_to_dict(report: BenchReport) -> dict:
    return {
        "mode": report.mode,
        "count": report.count,
        "aggregates": {
            "total_cost_usd": report.total_cost_usd,
            "mean_cost_usd": report.mean_cost_usd,
            "p50_latency_ms": report.p50_latency_ms,
            "p95_latency_ms": report.p95_latency_ms,
            "fallback_rate": report.fallback_rate,
            "provider_dist": report.provider_dist,
            "tier_dist": report.tier_dist,
            "tier_share": report.tier_share,
            "frontier_baseline_usd": report.frontier_baseline_usd,
            "savings_usd": report.savings_usd,
            "savings_pct": report.savings_pct,
        },
        "results": [
            {
                "id": r.id,
                "complexity": r.complexity,
                "provider": r.provider,
                "tier": r.tier,
                "model": r.model,
                "cost_usd": r.cost_usd,
                "latency_ms": r.latency_ms,
                "fallback": r.fallback,
                "attempts": r.attempts,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
            }
            for r in report.results
        ],
    }


_TABLE_MARKER = "<!-- BENCH_TABLE -->"


def _write_out(report: BenchReport, out: Path) -> None:
    if out.suffix == ".json":
        out.write_text(json.dumps(report_to_dict(report), indent=2) + "\n")
        return
    table = render_markdown(report)
    # If the target already has a BENCH_TABLE marker, replace everything after it
    # (keeps the docs/benchmarks.md methodology section intact). Otherwise write
    # the table standalone.
    if out.exists() and _TABLE_MARKER in out.read_text():
        head = out.read_text().split(_TABLE_MARKER)[0]
        out.write_text(head + _TABLE_MARKER + "\n\n" + table + "\n")
    else:
        out.write_text(table + "\n")


async def _main_async(args: argparse.Namespace) -> int:
    mode = "live" if args.live else "stub"
    if mode == "live":
        router = build_live_router()
        report = await run_benchmark(router, CASES, mode)
        await router.aclose()
    else:
        router = build_stub_router()
        report = await run_benchmark(router, CASES, mode)
        _apply_stub_latency(report)
        await router.aclose()

    print(render_markdown(report))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        _write_out(report, out)
        print(f"\nwrote {out}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cost-aware routing benchmark harness.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--stub", action="store_true", help="deterministic network-free run (default)"
    )
    mode.add_argument("--live", action="store_true", help="real providers from config (network)")
    parser.add_argument(
        "--out",
        metavar="PATH",
        help="write report to PATH (.md table or .json) in addition to stdout",  # noqa: E501
    )
    args = parser.parse_args(argv)
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
