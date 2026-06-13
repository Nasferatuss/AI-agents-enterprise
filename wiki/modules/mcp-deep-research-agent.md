---
type: module
status: active
sources: ["Дорожная карта.pdf"]
updated: 2026-06-13
---

# MCP Deep Research Agent

**Роль:** модуль №7 (post-MVP). Слой: MCP / Tool Gateway из [[service-oriented-core]].

**Что делает:** Planner → researcher → verifier → report generator. Агент делает
research report с источниками и trace.

**Sprint 7 — MCP Tool Gateway ✅ done 2026-06-13:** `platform/toolgateway`
(`workbench-toolgateway`) — security boundary **встроена в gateway** по [[adr-005-mcp-security-boundary]]:
- **registry** типизированных connectors (MCP-style: name + JSON-schema; **нет** generic
  shell-инструмента — no arbitrary shell структурно);
- **permission allowlist** на каждый вызов (denied-tool НЕ выполняется);
- **audit log** каждого вызова (tool/args/allowed/error/latency) — governance-артефакт.
3 sample-connector'а над bundled research-corpus: `web_search`, `fetch`, `kb_search`.

**Sprint 7.1 — Deep Research Agent ✅ done 2026-06-13:** `apps/deep_research`
(`workbench-app-research`) — predictable pipeline (ADR-007): **plan** (LLM→sub-questions) →
**research** (код прогоняет gateway-инструменты web_search→fetch под allowlist) → **report**
(LLM синтезирует cited-отчёт только по собранным источникам; verifier-поведение в промпте).
Возвращает report + sources + **gateway audit log как tool-trace**. API:
`GET /v1/apps/research/tools` (registry), `POST /v1/apps/research`. UI `/research`
(report, sources, tool-call audit). Прогон пишется в observability-trace.

**DoD выполнен:** агент проходит через 2–3 инструмента через единый gateway; делает research
report с источниками и trace (audit log).

**Real MCP (hardening, 2026-06-13):** теперь это не только MCP-style connectors —
есть **настоящий MCP client + server**. `mcp_server.py` (`FastMCP`) переотдаёт
corpus-инструменты по stdio JSON-RPC; `mcp_client.py` (stdio `ClientSession`)
коннектится к любому MCP-серверу, перечисляет его tools и регистрирует их в том же
gateway — под тем же **allowlist + audit** boundary. Opt-in через `WB_MCP_SERVER_COMMAND`
(пусто = in-process corpus, поведение по умолчанию). `GET /v1/apps/research/mcp/tools`
отдаёт live-список инструментов сервера. Round-trip покрыт тестами (bundled server
поднимается из самого процесса — без сети, CI-safe).
**Стек:** официальный MCP SDK (`mcp`), JSON-RPC over stdio, Agent Runtime, RAG, опц. web/search.

> MCP — слой стандартизации подключений к данным и tools, но проектировать с
> **security boundary**, allowlist и audit log: connectivity увеличивает поверхность риска.
> См. [[adr-005-mcp-security-boundary]] · [[mcp-tool-use]].

**Связи:** [[rag]], [[governance]], [[agent-observability-console]].

## Sources
- `Дорожная карта.pdf` стр. 13 (Sprint 7).
