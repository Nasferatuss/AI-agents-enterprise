# Enterprise AI Agent Workbench

Service-oriented platform for building, evaluating, and operating production-grade AI agents.
One core, ten demo apps — every module demonstrates the full engineering loop:
**context → tools → reasoning → action → eval → trace → governance → demo.**

> Status: **MVP complete** — service-oriented core + 4 MVP modules, hardened (Phase 4 QA).
> Roadmap: MVP → Portfolio (10 modules) → Showcase.

## What's built

**Platform core** (`platform/`): a cost-aware **model router** (local-first: Ollama on a
GPU box → cheap APIs → frontier, with fallback), an **agent runtime** (provider-agnostic
tool-calling loop), a **context engine** (prompt assembly + compaction), a **RAG core**
(chunking, local embeddings, Qdrant, hybrid RRF search), an **evaluation engine** (retrieval
metrics, citation accuracy, LLM judges, synthetic QA), a predictable **workflow orchestrator**
(state machine + human-in-the-loop approval gates), and an **observability layer** (a trace
for every run).

**MVP modules:**
1. **Workflow Orchestrator** — predictable workflows with approval gates & audit log → `/workflows`
2. **Text-to-SQL BI Agent** — question → guarded read-only SQL → result → explanation → `/text2sql`
3. **RAG Evaluation Lab** — RAG pipeline + strict retrieval/answer evals
4. **Observability Console** — cost, latency, failure taxonomy for every run → `/observability`

## Architecture

Monorepo around a **Service-Oriented Core**: shared platform capabilities (RAG, evals,
observability, context engine, governance, orchestration, model routing) are platform
services — never re-implemented inside individual demo apps.

```
platform/   platform layers: shared, gateway, runtime, rag, evals, orchestrator, observability
apps/       demo modules built on top of the core (text2sql)
ui/web      Next.js demo console (3 module pages)
infra/      Docker Compose
docs/       setup, demo walkthrough, security model
wiki/       knowledge base: architecture, ADRs, roadmap, risks (Obsidian-style, Russian)
sources/    immutable source documents the wiki is built from
```

Key decisions live in `wiki/decisions/` as ADRs (service-oriented monorepo, MVP scope,
hybrid local/API model split, read-only SQL safety, custom trace schema, predictable
orchestration, model-router design, deployment topology).

## Stack

Python 3.12 / FastAPI / Pydantic · uv workspace · PostgreSQL · Qdrant · Redis · SQLAlchemy ·
sqlglot · Next.js / React / TypeScript / Tailwind · Docker Compose · hybrid local/API LLM routing.

## Quickstart

```bash
make install   # uv sync + npm install
make qa        # lint + full test suite (incl. eval regression + SQL injection)
make seed      # populate the observability console with sample runs
make up        # full stack via Docker Compose (postgres, qdrant, redis, api)
make ui        # demo console on :3000
```

To wire up real models (local Ollama on a GPU box, or any provider key), see
[`docs/setup.md`](docs/setup.md). For a guided tour, see [`docs/demo.md`](docs/demo.md);
for the security model, [`docs/security.md`](docs/security.md).
