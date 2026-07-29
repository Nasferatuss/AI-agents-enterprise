---
type: concept
sources: ["Дорожная карта.pdf"]
updated: 2026-06-13
---

# Observability

Платформенный **Observability Layer**: traces, logs, token usage, latency, cost,
failure taxonomy. Сквозной MVP-приоритет.

**Trace model:** run → step → tool call → model call → error → cost (+ latency, tokens).
Начинать с custom schema → [[adr-006-custom-trace-schema]].

**Стек:** OpenTelemetry, Langfuse, structured logs, custom trace viewer → [[tech-stack]].

**Реализовано (Sprint 5, 2026-06-13):** `platform/observability` — custom trace
schema (один `traces` table: aggregate-колонки + JSON payload), запись best-effort на каждый
run, API + UI `/observability` (dashboard, failure taxonomy, trace detail) → [[adr-006-custom-trace-schema]].

**Модуль-витрина:** [[agent-observability-console]]. Питает [[incident-response-agent]]
(failed traces → RCA).

**Метрика:** runs with full trace 100%.

## Sources
- `Дорожная карта.pdf` стр. 3, 12.
