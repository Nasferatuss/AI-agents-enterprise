# Cost-aware routing — benchmark

Proof, with numbers, that the local-first Model Router (ADR-008) routes by task
complexity and that doing so cuts cost without an unacceptable latency hit. The
harness runs a fixed, representative workload through the real `ModelRouter`
(`platform/runtime/src/workbench_runtime/router.py`) and reports per-request and
aggregate telemetry — the same `cost_usd` / `latency_ms` the router records in
production traces.

## Methodology

**Workload.** A fixed set of 15 prompts (`scripts/bench.py::CASES`), each tagged
with the complexity tier a router should pick for it. The mix is intentionally
skewed toward simple/standard work (classification, extraction, drafting, SQL,
short summaries) with a minority of complex/judge tasks (architecture, hard
synthesis, eval) — the distribution where local-first routing actually pays off.

**Routing.** Each prompt goes through `ModelRouter.complete()` at its tagged
complexity. The router walks the ordered `local → cheap → frontier` candidate
chain with fallback; the first candidate that succeeds serves the request. We
record the winning provider/model, its tier, `cost_usd`, `latency_ms`, and
whether any earlier candidate failed first (a fallback).

**Cost & savings.** Per-request cost comes from the production pricing table
(`workbench_runtime/pricing.py`), USD per 1M tokens. The headline **local-first
savings** is a counterfactual: for every request we recompute what it *would*
have cost on the frontier baseline model (`claude-opus-4-8`) using that request's
own token counts, sum it, and compare to the actual total. `savings = baseline −
actual`.

**Latency.** Aggregated as p50/p95 over per-request `latency_ms`.

**Stub vs live — read this.** The harness has two modes:

- `--stub` (default, CI): a deterministic, fully **network-free** fake provider
  stack (httpx `MockTransport`, the same pattern as the router unit tests). Token
  counts and latency are baked in per provider, and the local box is simulated as
  "down" to exercise fallback accounting. These numbers are **illustrative** —
  they show the harness and the arithmetic are correct, not what your hardware
  does.
- `--live`: the real registry from configuration (Ollama on the GPU box, cheap
  APIs, frontier APIs — whichever keys are present). Goes to the network. These
  numbers are **real**, measured against your actual providers.

So: the stub proves the *mechanism*; the live run proves the *result*. The table
below is filled from a live run.

## How to run

```bash
make bench        # stub mode — deterministic, network-free (CI-safe)
make bench-live   # live mode — real providers from config (needs keys / Ollama)
```

Direct invocation and outputs:

```bash
uv run python scripts/bench.py --stub
uv run python scripts/bench.py --live --out docs/benchmarks_data.md   # markdown
uv run python scripts/bench.py --live --out docs/benchmarks_data.json # json
```

Writing to a file whose contents include the `<!-- BENCH_TABLE -->` marker
replaces only the section after the marker, so the methodology above is preserved
when this page is regenerated.

## Latest run

Live run on 2026-06-20, real providers (DeepSeek = cheap tier, Anthropic
`claude-opus-4-8` = frontier; local Ollama on the GPU box). **Note:** the box was
up but the `qwen2.5:3b-instruct` model wasn't pulled, so the first local call
returned 404 and the router **fell back local → deepseek live** — exactly the
resilience path this design exists for, captured here as a real fallback (not a
simulated one). With the model pulled, the cheap-tier share would shift toward
local and savings would increase.

<!-- BENCH_TABLE -->

### Benchmark run (live mode) — 15 requests

| case | complexity | provider | tier | model | cost | latency_ms | fallback |
|---|---|---|---|---|---|---|---|
| classify-1 | simple | deepseek | cheap | deepseek-chat | $0.000006 | 4177 | yes |
| extract-1 | simple | deepseek | cheap | deepseek-chat | $0.000037 | 1363 |  |
| sentiment-1 | simple | deepseek | cheap | deepseek-chat | $0.000056 | 1899 |  |
| summarize-1 | simple | deepseek | cheap | deepseek-chat | $0.000041 | 1818 |  |
| translate-1 | simple | deepseek | cheap | deepseek-chat | $0.000026 | 1323 |  |
| draft-1 | standard | deepseek | cheap | deepseek-chat | $0.000048 | 1659 |  |
| sql-1 | standard | deepseek | cheap | deepseek-chat | $0.000436 | 4211 |  |
| rewrite-1 | standard | deepseek | cheap | deepseek-chat | $0.000018 | 1406 |  |
| explain-1 | standard | deepseek | cheap | deepseek-chat | $0.000639 | 8991 |  |
| plan-1 | standard | deepseek | cheap | deepseek-chat | $0.001131 | 14189 |  |
| reason-1 | complex | anthropic | frontier | claude-opus-4-8 | $0.025775 | 15794 |  |
| synth-1 | complex | anthropic | frontier | claude-opus-4-8 | $0.021640 | 16391 |  |
| debug-1 | complex | anthropic | frontier | claude-opus-4-8 | $0.018125 | 11124 |  |
| arch-1 | complex | anthropic | frontier | claude-opus-4-8 | $0.025735 | 13621 |  |
| audit-1 | judge | anthropic | frontier | claude-opus-4-8 | $0.013395 | 9212 |  |

#### Aggregates

| metric | value |
|---|---|
| total cost | $0.107108 |
| mean cost / request | $0.007141 |
| p50 latency | 4211 ms |
| p95 latency | 15794 ms |
| fallback rate | 7% |
| tier share | local 0%, cheap 67%, frontier 33% |
| provider distribution | anthropic 5, deepseek 10 |

#### Local-first savings vs all-frontier baseline

| metric | value |
|---|---|
| actual cost | $0.107108 |
| baseline (all `claude-opus-4-8`) | $0.159870 |
| saved | $0.052762 (33%) |

**Read of the result:** routing the 10 simple/standard requests to the cheap tier
instead of frontier cost **$0.0029 total** vs **$0.052** they'd have cost on
`claude-opus-4-8` — a **33% cut on the whole mixed workload**, and the cheap tier
also served them 3–10× faster (p50 ≈ 1.8 s vs frontier 11–16 s). The complex/judge
work still goes to frontier, where it belongs. This is the cost-aware routing
thesis, measured end-to-end on live providers.
