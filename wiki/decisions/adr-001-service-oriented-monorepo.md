---
type: decision
status: active
sources: ["project roadmap (internal)"]
updated: 2026-06-07
---

# ADR-001 — Service-Oriented Core в monorepo

**Решение:** строить единый **Enterprise AI Agent Workbench** строго модульно —
как одну платформу с [[service-oriented-core]] и 10 demo-модулями.

**Не** как 10 отдельных репозиториев. **Не** как один неуправляемый монолит.

**Обоснование:** общие возможности ([[rag]], [[evals]], [[observability]],
[[mcp-tool-use]], context, policy, orchestration) — платформенные сервисы, не
дублируются в каждом модуле. Совпадает с индустрией (OpenAI: model+tools+guardrails+orchestration+evals; Anthropic: composable patterns, MCP).

**Следствие:** monorepo с `platform/` (слои) и `apps/` (модули). Риск поддержки
monorepo митигируется чёткой структурой, Makefile, Docker Compose, docs.

**Уточнение (2026-06-20):** ревью выявило горизонтальную связь app→app — флагман
`autonomous` импортировал SQL-guard/engine из `text2sql` и web-коннекторы из
`deep_research`. Это эрозия принципа (apps зависят от платформы, не друг от друга).
Исправлено выделением `platform/capabilities` (`workbench-capabilities`):
read-only SQL guard, schema reflection, sample BI database, governed live web —
общие capabilities, на которые теперь опираются и `text2sql`, и `deep_research`, и
`autonomous`. App→app зависимостей не осталось.

## Sources
- `project roadmap (internal)` p. 1–2, 23.
