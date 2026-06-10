---
type: concept
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# RAG

Платформенный сервис **RAG Core** в [[service-oriented-core]]: ingestion, chunking,
embeddings, hybrid search, reranking, citations.

**Стек:** Qdrant/pgvector, PyMuPDF, локальные embeddings (bge/e5/nomic) → [[tech-stack]].

**Где используется:** [[rag-evaluation-lab]] (основной), [[text-to-sql-rag-agent]] (schema/доки),
[[business-process-investigator]], [[compliance-risk-reviewer]], [[mcp-deep-research-agent]].

**Качество (метрики):** retrieval hit rate, citation accuracy, context precision/recall,
faithfulness, answer relevance, answer groundedness → [[evals]] · [[kpi-and-metrics]].

**Риск:** «чат с PDF» → акцент на eval lab, corrective RAG, citation accuracy, regression.
См. [[risk-register]].

## Sources
- `Дорожная карта.pdf` стр. 2, 10, 22.
