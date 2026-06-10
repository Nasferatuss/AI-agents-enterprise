---
type: module
status: draft
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# Incident Response Agent

**Роль:** модуль №10 (post-MVP). Замыкает цикл с [[agent-observability-console]].

**Что делает:** анализирует failed traces → классифицирует root cause → предлагает fix.
Для failed run создаётся RCA report.

**Sprint 9.1:** Incident Response Agent.
**DoD:** для failed run создаётся RCA report.
**Стек:** Observability Layer, Eval Engine.

**Риск:** слабость без реальных инцидентов → создать synthetic failed traces:
bad retrieval, SQL error, timeout, hallucination. См. [[risk-register]].

**Метрики:** RCA generated for failed runs 70%+/90%+, root cause classification accuracy,
fix recommendation usefulness → [[kpi-and-metrics]].
**Связи:** [[observability]], [[evals]], [[enterprise-workflow-orchestrator]].

## Sources
- `Дорожная карта.pdf` стр. 14 (Sprint 9.1).
