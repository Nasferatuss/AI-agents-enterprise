---
type: module
status: draft
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# Compliance & Risk Reviewer

**Роль:** модуль №6 (post-MVP).

**Что делает:** проверка документа по policy rules, risk scoring, рекомендации.
Документ получает risk report с объяснениями.

**Sprint 6.1:** Compliance Reviewer v0.
**DoD:** документ получает risk report с объяснениями.
**Стек:** Policy Engine, RAG, PII checks → [[governance]].

Помогает против риска «governance выглядит формально»: реальные policy gates —
PII, approval, tool permissions, risk report. См. [[risk-register]].

**Метрики:** PII detection rate, approval compliance, blocked unsafe tool calls → [[kpi-and-metrics]].
**Связи:** [[business-process-investigator]], [[governance]].

## Sources
- `Дорожная карта.pdf` стр. 13 (Sprint 6.1), стр. 20–22.
