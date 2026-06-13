---
type: module
status: active
sources: ["Дорожная карта.pdf"]
updated: 2026-06-13
---

# Compliance & Risk Reviewer

**Роль:** модуль №6 (post-MVP).

**Что делает:** проверка документа по policy rules, risk scoring, рекомендации.
Документ получает risk report с объяснениями.

**Sprint 6.1:** Compliance Reviewer v0. ✅ done 2026-06-13: `apps/compliance_reviewer`
(`workbench-app-compliance`). Архитектурный принцип: **risk score детерминированный и
rule-based** (defensible, не «LLM-vibes») — LLM пишет только narrative-объяснение.
- **Policy engine** (чистый, без LLM, протестирован): PII-детекция regex (email/phone/SSN/
  credit-card с Luhn/IPv4, значения **маскируются** в findings), policy-rules
  (forbidden_term / required_clause), детерминированный risk-score 0–100 → band
  low/medium/high/critical.
- **Reviewer**: deterministic findings + score → LLM пишет summary + recommendations
  (best-effort; без провайдера findings возвращаются как есть).
- API `POST /v1/apps/compliance/review`, страница `/compliance` (risk band/score, PII,
  violations, recommendations). Sample-доки в `examples/docs/`.
**DoD выполнен**: документ получает risk report с объяснениями. Усиливает governance —
реальные policy gates → [[governance]].
**Стек:** Policy Engine, RAG, PII checks → [[governance]].

Помогает против риска «governance выглядит формально»: реальные policy gates —
PII, approval, tool permissions, risk report. См. [[risk-register]].

**Метрики:** PII detection rate, approval compliance, blocked unsafe tool calls → [[kpi-and-metrics]].
**Связи:** [[business-process-investigator]], [[governance]].

## Sources
- `Дорожная карта.pdf` стр. 13 (Sprint 6.1), стр. 20–22.
