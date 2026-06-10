---
type: module
status: draft
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# MCP Deep Research Agent

**Роль:** модуль №7 (post-MVP). Слой: MCP / Tool Gateway из [[service-oriented-core]].

**Что делает:** Planner → researcher → verifier → report generator. Агент делает
research report с источниками и trace.

**Sprint 7 (1 нед):** MCP Tool Gateway — tool registry, tool permissions, sample
MCP-style connectors; агент вызывает 2–3 инструмента через единый gateway.
**Sprint 7.1:** Deep Research Agent.

**DoD:** агент проходит через 2–3 инструмента; делает research report с источниками и trace.
**Стек:** MCP SDK / JSON-RPC contracts, Agent Runtime, RAG, опц. web/search.

> MCP — слой стандартизации подключений к данным и tools, но проектировать с
> **security boundary**, allowlist и audit log: connectivity увеличивает поверхность риска.
> См. [[adr-005-mcp-security-boundary]] · [[mcp-tool-use]].

**Связи:** [[rag]], [[governance]], [[agent-observability-console]].

## Sources
- `Дорожная карта.pdf` стр. 13 (Sprint 7).
