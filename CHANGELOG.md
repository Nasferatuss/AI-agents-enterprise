# Changelog

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
