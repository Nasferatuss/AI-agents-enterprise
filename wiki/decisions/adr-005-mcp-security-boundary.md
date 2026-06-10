---
type: decision
status: active
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# ADR-005 — MCP security boundary

**Контекст:** [[mcp-tool-use]] / Tool Gateway стандартизует подключения к данным и tools,
но увеличивает security surface (риск Med/High).

**Решение:** проектировать tool-слой с явной security boundary:
- **tool allowlist** и **permissions**;
- **audit log** всех вызовов;
- **no arbitrary shell execution**.

**Обоснование:** Anthropic описывает MCP как открытый стандарт, но connectivity = риск;
governance должен быть встроен в gateway, а не пристроен сбоку. См. [[governance]] · [[risk-register]].

**Связи:** [[mcp-deep-research-agent]], Sprint 7 → [[phases-and-sprints]].

## Sources
- `Дорожная карта.pdf` стр. 13, 19.
