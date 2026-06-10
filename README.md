# Enterprise AI Agent Workbench

Service-oriented platform for building, evaluating, and operating production-grade AI agents.
One core, ten demo apps — every module demonstrates the full engineering loop:
**context → tools → reasoning → action → eval → trace → governance → demo.**

> Status: **Sprint 0 — platform skeleton.** Roadmap: MVP (core + 3 modules) → Portfolio (10 modules) → Showcase.

## Architecture

Monorepo around a **Service-Oriented Core**: shared platform capabilities (RAG, evals,
observability, MCP/tool gateway, context engine, policy/governance, orchestration) are
platform services — never re-implemented inside individual demo apps.

```
platform/   platform layers (gateway, shared; runtime/rag/evals/... arrive per sprint)
apps/       demo modules built on top of the core
ui/web      Next.js demo console
infra/      Docker Compose, CI
wiki/       knowledge base: architecture, ADRs, roadmap, risks (Obsidian-style, Russian)
sources/    immutable source documents the wiki is built from
docs/       generated/product docs
```

Key decisions live in `wiki/decisions/` (ADR-001 service-oriented monorepo,
ADR-002 MVP scope, ADR-003 hybrid local/API model split, …).

## Stack

Python 3.12 / FastAPI / Pydantic · uv workspace · PostgreSQL (pgvector) · Qdrant · Redis ·
Next.js / React / TypeScript / Tailwind · Docker Compose · hybrid local/API LLM routing.

## Quickstart

```bash
make install   # uv sync + npm install
make test      # pytest
make api       # gateway on :8000 (GET /healthz, /healthz/deps)
make up        # full stack via Docker Compose (postgres, qdrant, redis, api)
make ui        # demo console on :3000
```
