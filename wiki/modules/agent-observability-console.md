---
type: module
status: active
sources: ["Дорожная карта.pdf"]
updated: 2026-06-13
---

# Agent Observability Console

**Роль:** MVP-модуль №4, **сквозной** — proof of production thinking.
Слой: Observability из [[service-oriented-core]]. Концепция → [[observability]].

**Что делает:** логирует и визуализирует «мозг агента» по шагам.

**Sprint 5 (1 нед):** Trace Logging ✅ done 2026-06-13: `platform/observability`
(`workbench-observability`) — минимальная custom trace schema ([[adr-006-custom-trace-schema]]):
один `traces` table (queryable aggregate-колонки: kind/name/status/latency/cost/tokens/
num_steps/error + JSON `payload` для детального просмотра — НЕ нормализованный LangSmith-клон).
SQLAlchemy-async, DB-agnostic ([[adr-009-deployment-topology]]): sqlite-файл локально без
Docker, Postgres (asyncpg) в стеке `make up`. Запись best-effort на **каждый** run
(agent/workflow/eval) — outage trace-store не ломает запрос (logged+swallowed). Каждый
domain-пакет владеет своим маппингом (`*/tracing.py`), observability — чистый sink.
API: `GET /v1/observability/{summary,traces,traces/{id}}`.
**Sprint 5.1:** Observability UI ✅ done 2026-06-13: страница `/observability` —
dashboard (total runs, success rate, p95 latency, total cost), failure taxonomy,
таблица трейсов (kind/name/status/steps/latency/cost), детальный просмотр payload
(шаги run'а). **DoD модуля выполнен**: каждый run имеет trace, UI показывает шаги.

**DoD:** каждый агентный запуск имеет полный trace; UI показывает шаги.
**Стек:** OpenTelemetry/custom, PostgreSQL, Next.js (tables, timeline).

Начинать с **custom trace schema**, не строить LangSmith-клон → [[adr-006-custom-trace-schema]].

**Метрики:** runs with full trace 100%, p95 latency, cost per demo run → [[kpi-and-metrics]].
**Связи:** питает [[incident-response-agent]] (failed traces), используется всеми модулями.

## Sources
- `Дорожная карта.pdf` стр. 12 (Sprint 5), стр. 20 (риск observability).
