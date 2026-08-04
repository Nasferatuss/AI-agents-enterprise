# Changelog

## Unreleased — Local-model interop

Three defects found while driving the live flagships against Ollama on the GPU
box — the platform's own local-first default, and the path a reviewer without an
API key takes first.

- **A reasoning model returned nothing and nobody noticed.** Ollama puts a
  model's chain of thought in a non-standard `reasoning` field and leaves
  `content` empty; under a small `max_tokens` the whole budget goes to thinking.
  Callers received `""` — not an error — and reported an unexplainable parse
  failure (`/browse` stopped on step 1 with `could not parse a JSON action`).
  The OpenAI-compatible client now retries once asking the server to skip
  thinking, and raises a diagnostic error if the answer is still all thought.
  Local providers only: hosted APIs reject the parameter.
- **The local read timeout was hard-coded to the API default.** A cold or large
  local model (a 30B MoE loads ~18GB on first call) exceeded 120s, the router
  marked the box unhealthy and fell through to a paid provider — the opposite of
  local-first. Now `WB_LOCAL_READ_TIMEOUT_S`, still defaulting to 120s, and the
  short connect timeout that makes an offline box fail fast is unchanged.
- **The test suite read the developer's `.env`.** `conftest.py` neutralised
  `load_dotenv`, but `Settings` declares `env_file=".env"` and pydantic-settings
  reads it directly, so every `WB_*` value leaked in. With
  `WB_ROUTE_STANDARD_VIA_LOCAL=true` set — i.e. on any machine actually running
  the stack — two routing tests asserted the wrong chain and failed. The file is
  detached and all `WB_*` values stripped for the suite, with a sentinel test.

## Unreleased — Production hardening

Moving the demo-grade seams to real backends, plus the deploy-gating controls.

- **Real MCP client + server** (ADR-005) — the Tool Gateway can now source its
  tools from a real MCP server over stdio JSON-RPC instead of the in-process
  corpus. Ships both sides: a `FastMCP` server (`mcp_server.py`) re-exposing the
  research corpus, and a stdio `ClientSession` client that registers a server's
  tools under the same allowlist + audit boundary. Opt-in via
  `WB_MCP_SERVER_COMMAND`; off by default (corpus connectors). New
  `GET /v1/apps/research/mcp/tools` lists the live server tools.
- **Real Playwright computer-use** — the Guarded Computer-Use QA module drives a
  real headless chromium over a bundled `legacy_ui.html` behind the *same*
  observe/click/type gateway interface; the same two planted bugs surface through
  a real browser. Browser e2e runs in a dedicated CI job (`pytest -m playwright`,
  `make e2e`); deselected by default so `make test` needs no chromium.
- **Alembic migrations** for the trace store (`make migrate`); `init_db`
  auto-creates only on sqlite (dev/tests), Postgres schema is Alembic-owned.
- **Optional gateway auth & rate limiting** — `WB_API_KEY` gates `/v1/*`,
  `WB_RATE_LIMIT_PER_MIN` caps POSTs per client IP; both off by default.
- **Wiki** — the 5 external OpenAI/Anthropic sources referenced by the roadmap
  are now ingested into the concept pages with provenance and one flagged
  contradiction (`wiki/concepts/`).

### Hardening 2026-06-20 (post-review)

Acted on a multi-agent code/security/architecture/product review.

- **Security** — SSRF guard (`workbench_shared.netguard`) on every agent-driven
  fetch (autonomous, deep-research, live-browse): blocks private/loopback/
  link-local/metadata targets and re-validates each redirect hop. File sandbox
  hardened against symlink escape. Live-browse blocks submit after sensitive
  input (the type-then-Continue bypass). Prod fail-fast when auth/CORS unset;
  security headers; AST depth cap; Postgres password parameterized.
- **Architecture (ADR-010)** — durable run store (`agent_runs` + Alembic 0002):
  workflow HITL runs survive a gateway restart; async run model for the
  autonomous flagship (`POST /runs → 202`, poll `GET /runs/{id}`); Idempotency-Key
  on expensive submissions; router provider health cooldown (30s skip on a
  failed provider, reset on success — not a full circuit breaker: no
  half-open/failure-threshold states) + 429 backoff. Plus a
  distributed job queue (`workbench-jobs`: in-process + Redis/worker backends).
- **Service-Oriented Core (ADR-001)** — extracted `platform/capabilities`
  (SQL guard, schema reflection, sample BI database, governed web) so apps depend
  on the platform, not each other; removed the autonomous→text2sql/research
  app-to-app coupling.
- **Governance** — the Tool Gateway audit sink is wired to persist every tool
  call (allowed and denied) to the trace store.
- **Product** — published cost-aware routing benchmark (`docs/benchmarks.md`,
  `make bench`) with a real live run (33% cost cut on a mixed workload); README
  repositioned (production-style reference platform; modules grouped by depth).
- **Tests** — fixed a CI gap (the autonomous flagship's tests were missing from
  `testpaths`); suite network-free, ruff clean.

### Hardening round 2 (2026-06-20, second review)

- **Delivery guarantees** — race-safe idempotency via `UNIQUE(kind,
  idempotency_key)` (Alembic 0003) + `create_run` catching IntegrityError;
  at-least-once Redis queue (`BLMOVE` + ack + `reclaim()`); a startup
  **reconciler** that re-enqueues `pending`/`running` runs orphaned by a crash.
- **Security** — netguard now blocks CGNAT `100.64.0.0/10` (RFC 6598) and has
  dedicated unit tests (decimal/hex/octal/IPv6-mapped notations); Redis honors
  `WB_REDIS_PASSWORD`; `Job` fields pattern-validated and `dispatch` runs only
  registered kinds.
- **Product** — concurrency/throughput benchmark (`make bench-load`,
  `--concurrency N`) closing the "proof under load" gap; honest "provider health
  cooldown" naming (it is not a full circuit breaker); README test count unified.

### Hardening round 3 (2026-06-20, the residual backlog)

- **Hung runs** — a heartbeat (`touch_run` bumps `updated_at` during a run) + a
  periodic sweeper (`run_sweeper`) that fails runs idle past `WB_RUN_STUCK_TTL_S`;
  catches a worker that hangs without crashing.
- **Effectively-once** — the autonomous handler skips a run that already reached a
  terminal state, so at-least-once re-delivery doesn't redo finished (costly) work.
- **Reverse-proxy rate limiting** — `WB_TRUST_PROXY_HEADERS` lets the limiter bucket
  by `X-Forwarded-For` behind a trusted proxy (spoof-safe: off by default).
- **Qdrant auth** — `WB_QDRANT_API_KEY` (compose `QDRANT__SERVICE__API_KEY` + client),
  matching the Redis password support.

### Hardening round 4 (2026-06-21, credibility + distributed proof)

- **Hermetic test suite** — the root `conftest.py` now neuters `load_dotenv` and
  strips all provider keys, so the "no provider → 503" tests and `test_router` no
  longer depend on a developer's local `.env` leaking real keys. The suite is green
  from a clean clone whether or not `.env` is present (was 7 failed / 303 passed for
  a reviewer who cloned with keys; now 310 passed). Makes the "network-free" claim
  actually true on any machine.
- **Distributed delivery, demonstrated** — `docs/distributed.md` plus a deterministic
  end-to-end test (`test_two_workers_crash_midjob_reclaim_reruns_without_double_work`):
  worker A dies after the side effect but before the ack, worker B reclaims the orphan
  and re-delivers — two deliveries, one execution. Converts "distributed (in code)"
  into "distributed (proven + documented)". ADR-010 now states the in-process
  single-replica topology boundary explicitly.
- **Doc drift** — `docs/security.md` cited the pre-ADR-001 `apps/text2sql/safe_sql.py`
  path; the guard lives in `platform/capabilities/sql_guard.py`. README test count → 300+.

### Hardening round 5 (2026-06-21, security & correctness polish)

Acted on the round-3 multi-agent review's residual findings (Track A).

- **Timing-safe API-key compare** — `hmac.compare_digest` instead of `!=` (no byte-by-byte
  timing oracle).
- **RAG input hardening** — `{index}` path segment validated against
  `^[a-z0-9][a-z0-9_-]{0,63}$` before a Qdrant collection name is built from it; per-document
  text cap (200k chars) and per-request document cap (500) close an unbounded-ingest DoS.
- **Upload size limit** — compliance `review/file` rejects >5 MB with 413 *before* buffering/
  parsing, instead of reading an unbounded body into memory.
- **HSTS** — `Strict-Transport-Security` added to the always-on security headers.
- **Readiness-probe topology** — `/healthz/deps` no longer leaks internal host:port detail in
  `env=prod` (bare state only).
- **XSS in the console** — LLM-generated Mermaid SVG is sanitised with DOMPurify before
  `dangerouslySetInnerHTML` (`ui/web/app/process/page.tsx`).
- **Cleanups** — `assert resp` → explicit raise (survives `python -O`); three duplicate
  `_add_cost` helpers consolidated onto `workbench_runtime._util.add_cost`.

### Hardening round 6 (2026-06-21, robustness depth)

Track B — the distributed-systems edges the reviews named.

- **Bounded rate-limiter memory** — idle per-IP windows are now reaped periodically, so a
  scan/DDoS of many distinct IPs can't leak the limiter's dict unbounded for the process life.
- **Atomic stuck-run sweep** — `sweep_stuck_runs` is a single conditional
  `UPDATE … WHERE status='running'` instead of select-then-mutate, so a run that completes
  concurrently is never clobbered to `failed` (lost-update closed).
- **Fixed-width run timestamps** — the real fragility behind the "ISO strings sort as dates"
  note: `datetime.isoformat()` drops the fractional part at whole seconds, which mis-sorts
  within a second. `_fmt` now emits fixed-width `…%H:%M:%S.%fZ` for every writer (string
  columns kept deliberately — `agent_runs` is a transient operational table, sqlite is dev/test).
- **Router client lifecycle** — the gateway closes the shared model-router `httpx` client on
  shutdown (no connection-pool leak across reloads).
- **Explicit body threading** — `deep_research` now passes each fetched source body straight
  from its fetch result to the report stage, instead of recovering it from a module-global
  `BODY_CACHE` (the implicit cross-stage side channel is gone).

### Hardening round 7 (2026-06-21, product proof — Track C)

Turning "described" into "measured/shown" — the demo-facing gaps the product review named.

- **Concurrency benchmark filled** — the `LOAD_TABLE` placeholder in `docs/benchmarks.md` is
  now a real stub-mode run with **error bars across 4 trials** (speedup 6.1×–7.2×, median 7.1×;
  88% parallel efficiency; p95 essentially flat under load). Caption corrected (stub multi-trial,
  not "a live run").
- **Request lifecycle worked example** — `docs/request-lifecycle.md` traces one Text-to-SQL
  request through every layer and shows the actual `traces` row it writes (cost/latency/steps/
  scrubbed rows), with the failure-mode variants (provider fallback, rejected SQL, async path).
- **RAG eval report published** — `docs/rag-eval.md` publishes the real deterministic retrieval
  numbers (hit_rate 1.0, MRR 1.0, context_precision = 1/k) from the golden KB + the CI regression
  gate's floors and headroom. The numbers were only thresholds in code before; now they're a report.

### Hardening round 8 (2026-06-21, final-review residuals)

Closed the remaining low-severity findings from the final multi-agent review; +4 tests (322 passing).

- **Timing-safe approval token** — the workflow approve/reject gate now uses
  `hmac.compare_digest` (was `!=`), consistent with the gateway API-key gate.
- **No backend-topology leak on 503** — `NoProviderAvailableError`'s client message is now
  generic ("no model provider is currently available…"); the provider/model attempt list stays
  on `.attempts`/`.complexity` for server logs. Fixes the leak across all 13 routes at one point
  (and the incident classifier learned the new wording, with a regression row).
- **Input caps at the gateway boundary** — `/v1/chat` bounds message count, per-field size, and
  total transcript chars; RAG `search` query is capped (4k) before it reaches the embedder.
- **Qdrant client lifecycle** — the gateway closes the Qdrant client singleton on shutdown
  (only if a request built it), symmetric to the model-router client.
- **P0 regression sentinel** — `test_suite_is_hermetic_provider_keys_stripped` asserts in CI that
  provider keys are stripped and only the keyless `local` provider is enabled, so a future `.env`
  leak fails loudly here instead of silently un-hermeticizing the suite.

### Hardening round 9 (2026-06-21, the "to-10" increment — bounded, not Temporal)

The reviewers' remaining items, doing the genuinely-additive bounded parts and keeping true
exactly-once as the documented boundary. +4 tests (326 passing).

- **Dead-letter queue + max-retries** — `Job.attempts` is bumped on each reclaim; past
  `_MAX_ATTEMPTS` (5), or if the payload is unparseable, the job is parked in
  `workbench:jobs:dead` instead of looping forever. `dead_letter_count()` surfaces the depth.
  Standard queue hygiene (not durable-execution machinery — true exactly-once stays out, per ADR-010).
- **Heartbeat/TTL invariant guard** — `WB_RUN_HEARTBEAT_INTERVAL_S` is now config; the sweeper
  warns on startup if `WB_RUN_STUCK_TTL_S` isn't comfortably above it (a live-but-slow run would
  otherwise be swept as dead).
- **Recovery telemetry** — the worker logs reclaimed/reconciled/dead-letter counts on startup.
- **Reproducible cost figure** — the deterministic stub's local-first savings (44%, offline,
  reproducible from a clean clone) is documented alongside the live 33% and pinned as a regression
  gate (`test_stub_savings_are_reproducible`).

## v1.0.0 — Portfolio complete (2026-06-13)

The full roadmap: a service-oriented core plus all 10 demo modules, hardened.

### Platform core
- **Model router** (ADR-008) — local-first, cost-aware routing (local Ollama →
  cheap APIs → frontier) with graceful fallback and per-call cost telemetry.
- **Agent runtime** — provider-agnostic tool-calling loop; transcript renders to
  both Anthropic tool-use and OpenAI function-calling.
- **Context engine** — caching-friendly prompt assembly + transcript compaction.
- **RAG core** — loaders, heading-aware chunking, local embeddings, Qdrant,
  hybrid RRF search.
- **Evaluation engine** — retrieval metrics, citation accuracy, LLM judges,
  synthetic QA generation, a regression gate.
- **Workflow orchestrator** (ADR-007) — predictable state machine with
  human-in-the-loop approval gates and an audit log.
- **Observability** (ADR-006) — a custom trace schema; a trace for every run.
- **Tool gateway** (ADR-005) — registry + permission allowlist + audit log; no
  arbitrary shell.

### Modules (10)
1. Workflow Orchestrator · 2. Text-to-SQL BI Agent (ADR-004 read-only guards) ·
3. RAG Evaluation Lab · 4. Observability Console · 5. Business Process
Investigator · 6. Compliance & Risk Reviewer · 7. Deep Research Agent ·
8. Guarded Computer-Use QA · 9. Synthetic Eval Generator · 10. Incident Response.

### Quality & hardening (Phase 4)
- Eval regression CI gate, cross-layer e2e journey test.
- Independent security review + adversarial SQL suite — found & fixed two real
  SQL-guard bugs (un-caught tokenizer error; filesystem functions bypassing the
  table allowlist). Input caps, CORS tightening, trace-payload row scrubbing,
  optional approval-token gate. Known limits documented in `docs/security.md`.
- 193 tests; ruff clean; demo console (8 pages) builds.

### Engineering principles
Deterministic findings/scores/classification with the LLM only writing the
narrative; best-effort telemetry that never breaks a request; the security
boundary inside the gateway; provider-agnostic routing with fallback.
