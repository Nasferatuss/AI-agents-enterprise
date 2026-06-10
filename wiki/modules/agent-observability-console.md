---
type: module
status: draft
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# Agent Observability Console

**Роль:** MVP-модуль №4, **сквозной** — proof of production thinking.
Слой: Observability из [[service-oriented-core]]. Концепция → [[observability]].

**Что делает:** логирует и визуализирует «мозг агента» по шагам.

**Sprint 5 (1 нед):** Trace Logging — run, step, prompt, model call, tool call, error,
latency, token usage. **Sprint 5.1:** Observability UI — timeline, tool calls,
retrieved chunks, cost, latency, errors.

**DoD:** каждый агентный запуск имеет полный trace; UI показывает шаги.
**Стек:** OpenTelemetry/custom, PostgreSQL, Next.js (tables, timeline).

Начинать с **custom trace schema**, не строить LangSmith-клон → [[adr-006-custom-trace-schema]].

**Метрики:** runs with full trace 100%, p95 latency, cost per demo run → [[kpi-and-metrics]].
**Связи:** питает [[incident-response-agent]] (failed traces), используется всеми модулями.

## Sources
- `Дорожная карта.pdf` стр. 12 (Sprint 5), стр. 20 (риск observability).
