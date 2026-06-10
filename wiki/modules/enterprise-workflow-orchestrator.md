---
type: module
status: draft
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# Enterprise Workflow Orchestrator

**Роль:** ядро платформы. MVP-модуль №1 (см. [[adr-002-mvp-scope-3-modules]]).
Слой: Workflow Orchestrator из [[service-oriented-core]].

**Что делает:** state machine для агентных workflow — шаги, transitions, retries,
failure states, **human approval** gates.

**Sprint 4 (1 нед):** Orchestrator v0 — можно собрать workflow из 3–5 шагов и выполнить.
**Sprint 4.1:** Human-in-the-loop — approval gate перед risky action; UI показывает
pending approval и audit log → [[governance]].

**DoD:** workflow из 3–5 шагов выполняется; pending-approval и audit видны в UI.
**Стек:** LangGraph / custom state machine, FastAPI, Next.js, PostgreSQL.

> Anthropic рекомендует не усложнять агентные системы без необходимости и использовать
> composable patterns → начинать с **предсказуемых** workflow, а не автономной «магии».
> См. [[adr-007-predictable-orchestration]].

**Метрики:** workflow completion rate 70%+ (MVP) / 85%+ (portfolio) → [[kpi-and-metrics]].
**Связи:** [[agent-observability-console]] (traces), [[incident-response-agent]] (failed runs).

## Sources
- `Дорожная карта.pdf` стр. 11–12 (Sprint 4), стр. 23 (build order).
