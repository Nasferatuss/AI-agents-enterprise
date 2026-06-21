# Changelog

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
