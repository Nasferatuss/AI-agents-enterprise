---
type: concept
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# MCP / Tool Use

Платформенный **MCP / Tool Gateway**: servers, clients, tool registry, permissions.
Подключение SQL, browser, файлов, внешних API.

> Anthropic описывает MCP как открытый стандарт подключения AI-приложений к внешним
> системам и данным. Но это увеличивает security surface → проектировать с boundary:
> allowlist, permissions, audit log, no arbitrary shell → [[adr-005-mcp-security-boundary]].

**Стек:** MCP SDK / JSON-RPC style contracts → [[tech-stack]].

**Модуль-витрина:** [[mcp-deep-research-agent]] (Sprint 7). Tool call success rate
80%+/90% → [[kpi-and-metrics]] · [[governance]].

## Sources
- `Дорожная карта.pdf` стр. 3, 13.
