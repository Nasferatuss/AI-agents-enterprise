# apps/ — demo modules

Ten demo modules on top of the service-oriented core, arriving sprint by sprint.

MVP: `workflow-orchestrator` · `text-to-sql-rag-agent` · `rag-evaluation-lab`
(plus `agent-observability-console`, which cuts across all of them).

Each module is a thin application: a business scenario, the prompts, and a UI
page. All of the heavy machinery — RAG, evals, traces, governance, model routing
— lives in `platform/`.
