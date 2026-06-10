---
type: decision
status: active
sources: ["Дорожная карта.pdf"]
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
monorepo митигируется чёткой структурой, Makefile, Docker Compose, docs → [[risk-register]].

## Sources
- `Дорожная карта.pdf` стр. 1–2, 23.
