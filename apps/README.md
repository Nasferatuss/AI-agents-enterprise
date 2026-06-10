# apps/ — demo modules

Десять demo-модулей поверх Service-Oriented Core. Появляются по спринтам
(см. `wiki/roadmap/phases-and-sprints.md`):

MVP: `workflow-orchestrator` · `text-to-sql-rag-agent` · `rag-evaluation-lab`
(+ сквозной `agent-observability-console`).

Каждый модуль — тонкое приложение: бизнес-сценарий, промпты, UI-страница.
Вся тяжёлая механика (RAG, evals, traces, governance, model routing) — в `platform/`.
