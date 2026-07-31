---
type: concept
sources: ["project roadmap (internal)"]
updated: 2026-06-10
---

# RAG

Платформенный сервис **RAG Core** в [[service-oriented-core]]: ingestion, chunking,
embeddings, hybrid search, reranking, citations.

## RAG Core v0 — реализован (Sprint 2, 2026-06-10)

`platform/rag` (`workbench-rag`):
- **Loaders**: markdown/txt + PDF (pypdf); `Document` → heading-aware **chunking**
  (chunk не пересекает заголовок; длинные секции пакуются ~400 токенов, overlap 50).
- **Embeddings**: локально через Ollama на 4090 (`nomic-embed-text`,
  `WB_EMBEDDING_MODEL`) по [[adr-003-local-api-model-split]]; `HashEmbedder` —
  детерминированный несемантический fallback для тестов/dev без GPU
  (`WB_EMBEDDINGS_BACKEND=hash`).
- **Store**: Qdrant (`AsyncQdrantClient`; `:memory:` в тестах — Docker не нужен).
- **Hybrid search**: RRF-fusion dense (cosine) + BM25 (in-process на demo-масштабе;
  при росте корпуса — Qdrant sparse vectors, интерфейс не меняется).
- **API**: `GET /v1/rag/indexes` · `POST /v1/rag/indexes/{name}/documents` ·
  `POST /v1/rag/indexes/{name}/search` (top_k, hybrid on/off).
- Слот `retrieved` в `run_agent()` ([[context-engineering]]) готов принимать chunks.

Не вошло в v0 (→ Sprint 2.1+): reranker (bge-reranker), citations, corrective RAG.

**Стек:** Qdrant/pgvector, PyMuPDF, локальные embeddings (bge/e5/nomic) → [[tech-stack]].

**Где используется:** [[rag-evaluation-lab]] (основной), [[text-to-sql-rag-agent]] (schema/доки),
[[business-process-investigator]], [[compliance-risk-reviewer]], [[mcp-deep-research-agent]].

**Качество (метрики):** retrieval hit rate, citation accuracy, context precision/recall,
faithfulness, answer relevance, answer groundedness → [[evals]].

**Риск:** «чат с PDF» → акцент на eval lab, corrective RAG, citation accuracy, regression.

## Sources
- `project roadmap (internal)` p. 2, 10, 22.
