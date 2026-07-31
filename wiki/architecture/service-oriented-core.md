---
type: architecture
sources: ["project roadmap (internal)"]
updated: 2026-06-07
---

# Service-Oriented Core

Главный архитектурный паттерн проекта. См. [[adr-001-service-oriented-monorepo]].

**Принцип:**
- есть единое ядро платформы;
- каждый AI-модуль подключается как отдельный сервис / app;
- общие возможности не дублируются;
- [[rag]], [[evals]], [[observability]], [[mcp-tool-use]], context, policy и orchestration —
  это не куски внутри каждого проекта, а **общие платформенные сервисы**.

Это совпадает с индустрией: OpenAI описывает агентов через model + tools + instructions/guardrails
и подчёркивает orchestration и evals; Anthropic — composable agentic patterns и MCP как
открытый стандарт подключения к данным и tools.

## Слои платформы (`platform/`)

| Слой | Назначение |
|------|-----------|
| **UI / Demo Console** | Единый интерфейс запуска сценариев, просмотра traces, evals, результатов |
| **API Gateway** | Единая точка входа для UI и внешних клиентов |
| **Workflow Orchestrator** | Состояния, шаги, retry, human approval, branching → [[enterprise-workflow-orchestrator]] |
| **Agent Runtime** | Запуск агентов, tools, memory, instructions, model routing |
| **Context Engine** | Управление контекстом, summaries, retrieval, compression, memory → [[context-engineering]] |
| **RAG Core** | Ingestion, chunking, embeddings, hybrid search, reranking → [[rag]] |
| **MCP / Tool Gateway** | Подключение инструментов: SQL, browser, файлы, внешние API → [[mcp-tool-use]] |
| **Evaluation Engine** | RAG/agent/SQL evals, synthetic datasets → [[evals]] |
| **Observability Layer** | Traces, logs, token usage, latency, cost, failure taxonomy → [[observability]] |
| **Policy / Governance Engine** | Guardrails, allow/deny, PII checks, approval gates → [[governance]] |
| **Demo Apps** | 10 бизнес-сценариев поверх ядра → [[00_index]] |
| **shared** | config, db, events, schemas, utils |

## Принцип каждого модуля
Каждый модуль показывает не «модель ответила», а полный инженерный цикл:
**context → tools → reasoning → action → eval → trace → governance → demo.**

## Структура репозитория
Monorepo: `docs/` · `platform/` (слои выше) · `apps/` (10 модулей) · `ui/web` ·
`examples/` (sample data) · `data/` (raw/processed/vector_store/eval_results) ·
`infra/` (docker, github-actions, terraform_optional) · `tests/` (integration, e2e, eval_regression, security).

## Sources
- `project roadmap (internal)` p. 1–7 (концептуальная архитектура, directory map).
