---
type: module
status: active
sources: ["Дорожная карта.pdf"]
updated: 2026-06-13
---

# Incident Response Agent

**Роль:** модуль №10 (post-MVP). Замыкает цикл с [[agent-observability-console]].

**Что делает:** анализирует failed traces → классифицирует root cause → предлагает fix.
Для failed run создаётся RCA report.

**Sprint 9.1:** Incident Response Agent. ✅ done 2026-06-13: `apps/incident_response` —
**замыкает цикл с observability**: читает failed-трейсы из trace store, **детерминированно
классифицирует root cause** (правила над kind/status/error/payload: policy_rejection,
loop_no_progress, provider_unavailable, sql_error, tool_denied, scenario_failures,
low_eval_quality, unknown) + evidence; LLM пишет только narrative RCA (summary + fix
recommendation), как в [[compliance-risk-reviewer]]. API `GET /v1/apps/incidents` (failed runs
+ root cause), `POST /v1/apps/incidents/{id}/rca`. UI `/incidents`. Synthetic failed-трейсы для
демо генерит `make seed` (sql_error / provider_unavailable / low_eval_quality / loop / rejected).
**DoD выполнен:** для failed run создаётся RCA report.
**Стек:** Observability Layer, Eval Engine.

**Риск:** слабость без реальных инцидентов → создать synthetic failed traces:
bad retrieval, SQL error, timeout, hallucination.

**Метрики:** RCA generated for failed runs 70%+/90%+, root cause classification accuracy,
fix recommendation usefulness.
**Связи:** [[observability]], [[evals]], [[enterprise-workflow-orchestrator]].

## Sources
- `Дорожная карта.pdf` стр. 14 (Sprint 9.1).
