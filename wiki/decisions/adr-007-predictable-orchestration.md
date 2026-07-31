---
type: decision
status: active
sources: ["project roadmap (internal)"]
updated: 2026-06-07
---

# ADR-007 — Предсказуемая оркестрация, не автономная «магия»

**Решение:** [[enterprise-workflow-orchestrator]] начинается с **предсказуемых**
workflow (явные шаги, transitions, retries, approval gates), а не с полностью
автономного агента.

**Обоснование:** Anthropic рекомендует не усложнять агентные системы без необходимости
и использовать **composable patterns**. Это также снижает риск «слишком много технологий»
и нестабильности.

**Следствие:** human-in-the-loop approval перед risky action (Sprint 4.1) → [[governance]].

## Sources
- `project roadmap (internal)` p. 11–12.
