---
type: architecture
sources: ["project roadmap (internal)"]
updated: 2026-06-07
---

# Tech Stack 2026

| Направление | Стек | Почему |
|-------------|------|--------|
| Frontend | Next.js, React, TypeScript, Tailwind, shadcn/ui | Быстрый профессиональный dashboard / demo-console |
| Backend API | Python, FastAPI, Pydantic, SQLAlchemy | Быстрая разработка AI/backend-сервисов |
| Agent Runtime | LangGraph или своя state-machine; опц. OpenAI Agents SDK | Graph/stateful workflows, multi-step, tool calling |
| LLM Gateway | LiteLLM или свой model-router | Единый слой для локальных и внешних моделей |
| Local LLM | Ollama / llama.cpp / vLLM; Qwen/Llama/Mistral 7B–8B quantized | Реалистично для RTX 4070 8GB |
| External LLM | OpenAI / Anthropic / Google — optional hybrid | Сложный reasoning/eval, где локальной модели мало |
| Embeddings | bge-small/base, e5, nomic-embed; локально | Дёшево, быстро, реалистично |
| Vector DB | Qdrant или pgvector | Qdrant удобен для RAG; pgvector проще в едином Postgres |
| Relational DB | PostgreSQL | SQL-agent, traces, evals, configs, audit logs |
| Cache / Queue | Redis | Очереди, временное состояние, rate limits |
| Document Parsing | unstructured, pymupdf, python-docx, pandas/openpyxl | PDF, Excel, документы |
| Browser / Computer Use | Playwright + screenshot/action traces; опц. computer-use API | Guarded QA-agent по legacy UI |
| Evaluation | DeepEval, Ragas, promptfoo, custom harness | RAG/agent/SQL evaluation |
| Observability | OpenTelemetry, Langfuse, structured logs, custom trace viewer | Latency, cost, tool calls, errors |
| Security / Governance | policy engine на YAML/JSON, PII checks, allowlist tools, approval gates | Enterprise-readiness |
| DevOps | Docker Compose (local), GitHub Actions, GHCR, опц. Terraform | Portfolio-grade production style |
| Cloud | VPS / Hetzner / Fly.io / Render / опц. AWS/GCP/Azure | Публичное demo; MVP можно локально |
| Mobile | Не делать native; responsive web/PWA | Не ключевая ценность |

## Ограничение RTX 4070 8GB
Нельзя строить roadmap вокруг тяжёлых локальных LLM (30B/70B) без серьёзных компромиссов.
Подход → [[adr-003-local-api-model-split]]:
- **локально:** embeddings, reranker, 7B/8B quantized LLM, простые агенты;
- **гибридно:** сложный reasoning, judge/eval, computer-use — через внешние API;
- архитектура переключает модели через **model-router**.

## Sources
- `project roadmap (internal)` p. 3–4.
