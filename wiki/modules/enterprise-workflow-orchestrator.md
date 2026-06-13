---
type: module
status: active
sources: ["Дорожная карта.pdf"]
updated: 2026-06-13
---

# Enterprise Workflow Orchestrator

**Роль:** ядро платформы. MVP-модуль №1 (см. [[adr-002-mvp-scope-3-modules]]).
Слой: Workflow Orchestrator из [[service-oriented-core]].

**Что делает:** state machine для агентных workflow — шаги, transitions, retries,
failure states, **human approval** gates.

**Sprint 4 (1 нед):** Orchestrator v0 — можно собрать workflow из 3–5 шагов и выполнить.
✅ done 2026-06-13: `platform/orchestrator` (`workbench-orchestrator`) — предсказуемая
state machine по [[adr-007-predictable-orchestration]]:
- **Step** = async-функция над shared state → возвращает updates для merge; **transitions**
  явные (`next` = имя шага / branch-функция над state / None=конец); **retries** per-step
  с задержкой; глобальный step-budget против циклов в ветвлениях.
- Control flow детерминированный и auditable (LLM не решает граф): каждый StepAttempt
  пишется в `WorkflowRun` (статус, latency, error, updates) — семя [[adr-006-custom-trace-schema]].
- Demo-workflow `content_brief` (validate → draft → judge-review → revise-loop → finalize)
  показывает composable pattern: LLM-вызовы через [[adr-008-model-router-design]] **внутри**
  шагов (draft=standard, review=judge-tier), граф снаружи.
- **API**: `GET /v1/workflows`, `POST /v1/workflows/{name}/run`, `GET /v1/workflows/runs[/{id}]`.

**Sprint 4.1:** Human-in-the-loop ✅ done 2026-06-13: approval gate как свойство шага
(`requires_approval`) — движок **приостанавливается ДО** выполнения gated-шага
(`awaiting_approval`, ничего рискованного ещё не произошло); human делает approve
(run продолжается, gated-шаг выполняется) или reject (run → `rejected`, шаг не запускается).
Каждое решение пишется в `run.approvals` (actor, decision, reason, timestamp) — audit log →
[[governance]]. Движок стал resumable (`execute` + `resume`). Demo-workflow `access_request`
(validate → assess-risk через LLM → **gate** → grant): рискованное действие за человеческим
approval, risk assessment виден ревьюеру. API: `POST /v1/workflows/runs/{id}/{approve,reject}`.
UI-страница `/workflows`: запуск, pending-approval с risk assessment + кнопки approve/reject,
audit log, step trace. **DoD модуля №1 выполнен**: workflow из 3–5 шагов выполняется,
pending-approval и audit видны в UI.

**DoD:** workflow из 3–5 шагов выполняется; pending-approval и audit видны в UI.
**Стек:** LangGraph / custom state machine, FastAPI, Next.js, PostgreSQL.

> Anthropic рекомендует не усложнять агентные системы без необходимости и использовать
> composable patterns → начинать с **предсказуемых** workflow, а не автономной «магии».
> См. [[adr-007-predictable-orchestration]].

**Метрики:** workflow completion rate 70%+ (MVP) / 85%+ (portfolio) → [[kpi-and-metrics]].
**Связи:** [[agent-observability-console]] (traces), [[incident-response-agent]] (failed runs).

## Sources
- `Дорожная карта.pdf` стр. 11–12 (Sprint 4), стр. 23 (build order).
