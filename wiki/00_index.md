---
type: index
sources: ["Дорожная карта.pdf"]
updated: 2026-06-10
---

# Enterprise AI Agent Workbench — Index

Модульная платформа-портфолио, демонстрирующая production-style AI Engineering:
agentic workflow, RAG, Text-to-SQL, MCP/tool use, computer-use, evaluation,
observability, governance, incident response, orchestration.

**Главная цель:** не SaaS, а публичный инженерный артефакт, показывающий
способность *проектировать AI-системы вокруг LLM*, а не просто «вызывать LLM».

**North Star Metric:** число завершённых production-grade модулей, у каждого из которых
есть архитектурная схема, рабочее demo, trace, eval-метрики, README, limitations, recorded demo.
- MVP: ядро + **3** модуля высокой глубины.
- Portfolio: **10** модулей на едином [[service-oriented-core]].

## Статус разработки
**Sprint 0 — Repo & Platform Skeleton: done (2026-06-10).** Monorepo живёт в
[github.com/Nasferatuss/AI-agents-enterprise](https://github.com/Nasferatuss/AI-agents-enterprise):
uv workspace (`platform/shared` + `platform/gateway` + `platform/runtime`), FastAPI gateway,
Docker Compose (pgvector, Qdrant, Redis, api), Next.js demo console (`ui/web`).

**Sprint 1 — Agent Runtime + Model Router: done (2026-06-10).** `platform/runtime`
([[adr-008-model-router-design]]): local-first router (local Ollama/4090 → cheap DeepSeek/Kimi →
frontier Claude/GPT, fallback, cost-телеметрия) + agent loop с tool calling — provider-agnostic
transcript (Anthropic tool use ↔ OpenAI function calling), pydantic-валидация аргументов tools,
AgentRun-трейс каждого шага (семя [[adr-006-custom-trace-schema]]). Gateway: `/v1/models`,
`/v1/chat`, `/v1/agents`, `/v1/agents/{name}/run` (+ demo-агент с calculator/utc_now).
**Sprint 1.1 — Context Engine v0: done (2026-06-10).** Builder system prompt из частей
(instructions/memory/retrieved/task_state, caching-friendly порядок), compaction старых
ходов через simple-tier (бесплатная суммаризация), контекст и события компакции
сохраняются в `AgentRun.context` → [[context-engineering]].
**Sprint 2 + 2.1 — RAG Core + RAG Eval v0: done (2026-06-10).** `platform/rag`
(loaders, chunking, локальные embeddings, Qdrant, hybrid RRF) + `platform/evals`
(retrieval-метрики, citation accuracy, LLM-judges на judge-tier, synthetic QA,
отчёты в data/eval_results) → [[rag]] · [[rag-evaluation-lab]]. ADR-009: сервис на Mac,
GPU-машина = inference (инструкция: `docs/setup.md`).
**Sprint 3 + 3.1 — Text-to-SQL Agent + BI UI: done (2026-06-12).** `apps/text2sql`
(sqlglot-гарды по [[adr-004-readonly-sql-safety]], schema-aware агент, API) + страница
`/text2sql` в demo console. **DoD модуля №2 выполнен** → [[text-to-sql-rag-agent]].
**Sprint 4 — Workflow Orchestrator v0: done (2026-06-13).** `platform/orchestrator` —
предсказуемая state machine ([[adr-007-predictable-orchestration]]): steps/transitions/retries/
branching, step-budget, каждый шаг в `WorkflowRun`-трейсе; demo-workflow `content_brief`
(draft → judge-review → revise-loop) поверх [[adr-008-model-router-design]]; API `/v1/workflows/*`
→ [[enterprise-workflow-orchestrator]] (status: active). **Все 3 MVP-модуля + ядро готовы по v0.**
Следующий шаг: **Sprint 4.1 — Human-in-the-loop approval** ([[governance]]) либо
Sprint 5 — Trace Logging + Observability UI. Детали → [[phases-and-sprints]].

## Архитектура
- [[service-oriented-core]] — главный архитектурный паттерн
- [[tech-stack]] — стек 2026 и ограничение RTX 4070 8GB

## Модули (10) — в рекомендуемом порядке сборки
| # | Модуль | Статус | MVP |
|---|--------|--------|-----|
| 1 | [[enterprise-workflow-orchestrator]] | active | ✅ ядро |
| 2 | [[text-to-sql-rag-agent]] | active | ✅ |
| 3 | [[rag-evaluation-lab]] | active | ✅ |
| 4 | [[agent-observability-console]] | draft | ✅ сквозной |
| 5 | [[business-process-investigator]] | draft | |
| 6 | [[compliance-risk-reviewer]] | draft | |
| 7 | [[mcp-deep-research-agent]] | draft | |
| 8 | [[guarded-computer-use-qa-agent]] | draft | |
| 9 | [[synthetic-eval-generator]] | draft | |
| 10 | [[incident-response-agent]] | draft | |

## Сквозные концепции
[[rag]] · [[evals]] · [[observability]] · [[governance]] · [[mcp-tool-use]] · [[context-engineering]] · [[computer-use]]

## Решения (ADR)
- [[adr-001-service-oriented-monorepo]]
- [[adr-002-mvp-scope-3-modules]]
- [[adr-003-local-api-model-split]]
- [[adr-004-readonly-sql-safety]]
- [[adr-005-mcp-security-boundary]]
- [[adr-006-custom-trace-schema]]
- [[adr-007-predictable-orchestration]]
- [[adr-008-model-router-design]]
- [[adr-009-deployment-topology]]

## Планирование
- [[phases-and-sprints]] — Discovery → Design → Dev (Sprint 0–10) → QA → Launch → Post-Launch
- [[kpi-and-metrics]] — технические, AI-quality и portfolio метрики
- [[budget-and-resources]] — финансовый план
- [[risk-register]] — реестр рисков

## Источники
- `sources/Дорожная карта.pdf` — полный roadmap проекта (24 стр.)
  Внешние ссылки из источника: [OpenAI — Practical guide to building AI agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/),
  [OpenAI — Evals](https://developers.openai.com/api/docs/guides/evals),
  [OpenAI — Computer use](https://developers.openai.com/api/docs/guides/tools-computer-use),
  [Anthropic — MCP](https://www.anthropic.com/news/model-context-protocol),
  [Anthropic — Building effective agents](https://www.anthropic.com/research/building-effective-agents).
