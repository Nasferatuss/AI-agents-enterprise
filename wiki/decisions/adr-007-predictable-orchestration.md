---
type: decision
status: active
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# ADR-007 — Предсказуемая оркестрация, не автономная «магия»

**Решение:** [[enterprise-workflow-orchestrator]] начинается с **предсказуемых**
workflow (явные шаги, transitions, retries, approval gates), а не с полностью
автономного агента.

**Обоснование:** Anthropic рекомендует не усложнять агентные системы без необходимости
и использовать **composable patterns**. Это также снижает риск «слишком много технологий»
и нестабильности → [[risk-register]].

**Следствие:** human-in-the-loop approval перед risky action (Sprint 4.1) → [[governance]].

## Sources
- `Дорожная карта.pdf` стр. 11–12.
