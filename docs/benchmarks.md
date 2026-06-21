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

**Reproducible offline figure.** Because the stub is fully deterministic, its
local-first savings are a fixed, offline-reproducible number: **44%** ($0.0624 actual
vs $0.112 all-frontier baseline) on the 15-case mix. That is not the headline (the
*live* run's **33%** on real providers is), but it is the number anyone can reproduce
from a clean clone with no keys — and it is pinned as a regression gate in
`tests/test_bench.py::test_stub_savings_are_reproducible`, so a routing/pricing change
that moves it fails CI instead of silently shifting the published figure. The two
differ because token mixes differ between the baked stub and live providers; both
confirm the same thesis (cheap-tier routing of simple/standard work cuts cost).

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

## Concurrency / throughput

The cost benchmark above proves **correctness** — right tier, right price, right
fallback — but it runs strictly **sequentially**, one `router.complete()` after the
next. That says nothing about how the router behaves when many requests arrive at
once, which is the senior question for any production routing layer. This section
closes the **"proof under load"** gap: it measures the router under concurrent
traffic and reports throughput, not just per-request cost.

**What we measure.** A larger workload (the 15 `CASES` tiled up to `--requests` M,
default 48, preserving the complexity mix) is replayed twice through the *same*
router:

1. **Sequential** (`concurrency = 1`) — the baseline.
2. **Concurrent** (`concurrency = N`) — up to N `router.complete()` calls in flight
   at once, bounded by an `asyncio.Semaphore(N)` over `asyncio.gather`.

For each phase we record **wall-clock total**, **throughput (requests/sec)**, and
latency **p50/p95** under that contention. We then derive:

- **speedup** = sequential wall-clock ÷ concurrent wall-clock,
- **parallel efficiency** = speedup ÷ N (how close to linear scaling),
- **p95 degradation** = concurrent p95 ÷ sequential p95 (latency cost of load).

**Why this is the proof.** Concurrency is real *iff* the concurrent wall-clock falls
well below the **sum** of per-request latencies (the serial lower bound): N
overlapping awaits finish in ≈ max, not ≈ sum. The harness measures exactly that, so
a speedup > 1 with bounded p95 degradation is direct evidence the router sustains
parallel load on its async path — not a claim, a measurement. The unit test
(`tests/test_bench.py::test_load_is_actually_parallel`) asserts this property in CI.

**Stub vs live — read this (again).** Same split as the cost benchmark, with one
deliberate difference:

- `--stub` (default, CI): a **network-free** async fake transport that `await`s a
  real, scaled-down per-provider `asyncio.sleep` per request. Every host is kept
  **up** (unlike the cost stub, which downs `local` to test fallback) so the numbers
  reflect **concurrency, not fallback**. The sleeps are real, so the speedup is
  genuinely measured — but the absolute throughput is **illustrative** (it reflects
  the synthetic delays, not your providers).
- `--live`: the real registry. Concurrency now contends for real provider sockets,
  rate limits and the local GPU box, so throughput and p95 degradation are **real**.

So: the stub proves the *mechanism scales*; the live run proves the *throughput you
actually get*. The table below (`<!-- LOAD_TABLE -->`) is filled from **stub mode across
4 trials** — the speedup is genuinely measured (real `asyncio.sleep`s overlap), so it
demonstrates the async path parallelizes; the absolute req/s is illustrative. A `--live`
run replaces it with real provider throughput.

**How to run.**

```bash
make bench-load                                  # stub, concurrency 8 (CI-safe)
uv run python scripts/bench.py --concurrency 8 --stub
uv run python scripts/bench.py --concurrency 16 --requests 96 --live \
    --out docs/benchmarks_load.md                # live; .md table or .json
```

<!-- LOAD_TABLE -->

### Load run (stub mode) — 48 requests, concurrency 8

Representative trial (median speedup of 4):

| phase | concurrency | wall-clock (s) | throughput (req/s) | p50 (ms) | p95 (ms) | mean (ms) | errors |
|---|---|---|---|---|---|---|---|
| sequential | 1 | 2.587 | 18.55 | 22 | 123 | 53 | 0 |
| concurrent | 8 | 0.367 | 130.91 | 23 | 123 | 54 | 0 |

#### Concurrency effect

| metric | value |
|---|---|
| speedup (serial wall / concurrent wall) | 7.06× |
| parallel efficiency (speedup / concurrency) | 88% |
| p95 latency under load vs serial | 1.00× |
| throughput gain | 18.55 → 130.91 req/s |

#### Variance across 4 trials (error bars)

The same workload run 4× (the timing-sensitive numbers vary; the *property* — speedup ≫ 1
with bounded p95 — does not):

| metric | min | median | max |
|---|---|---|---|
| speedup | 6.11× | 7.06× | 7.22× |
| parallel efficiency | 76% | 88% | 90% |
| concurrent p95 / serial p95 | 0.98× | 1.00× | 1.26× |

**Read of the result:** at concurrency 8 the 48-request workload finishes ~7× faster than
sequential (≈88% of ideal linear scaling) with p95 latency essentially unchanged under load.
That is direct evidence the router's async path overlaps requests rather than serializing
them — the concurrent wall-clock (~0.37 s) is far below the serial lower bound (the **sum**
of per-request latencies, ~2.59 s). The property is asserted in CI by
`tests/test_bench.py::test_load_is_actually_parallel`; the absolute throughput is stub-illustrative.

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
