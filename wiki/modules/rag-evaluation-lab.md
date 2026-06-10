---
type: module
status: draft
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# Enterprise RAG Evaluation Lab

**Роль:** MVP-модуль №3 — демонстрация зрелого AI Engineering. Отличает проект от
«обычного чата с PDF» (см. [[risk-register]]).

**Что делает:** [[rag]] pipeline + строгая оценка качества retrieval и ответов.

**Sprint 2 (1 нед):** RAG Core — ingestion, chunking, embeddings, vector search, citations.
**Sprint 2.1:** RAG Eval v0 — retrieval hit rate, citation accuracy, answer groundedness;
первый eval report по sample documents.

**DoD:** документы загружаются/индексируются/находятся релевантные chunks; есть eval report.
**Стек:** Qdrant/pgvector, PyMuPDF, embeddings, Ragas/DeepEval/custom.

> OpenAI и Anthropic выделяют evals как обязательную часть надёжных AI-приложений,
> особенно для многошаговых агентов с tools и состоянием.

Акцент на eval lab, corrective RAG, citation accuracy, regression — чтобы не выглядеть
«чатом с PDF».

**Метрики:** retrieval hit rate 70%+/85%+, citation accuracy 70%+/85%+, context
precision/recall, faithfulness, answer relevance → [[kpi-and-metrics]] · [[evals]].
**Связи:** [[synthetic-eval-generator]] (датасеты), [[text-to-sql-rag-agent]].

## Sources
- `Дорожная карта.pdf` стр. 10 (Sprint 2), стр. 19–20 (риски), стр. 22 (метрики).
