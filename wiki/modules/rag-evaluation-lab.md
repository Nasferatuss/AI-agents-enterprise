---
type: module
status: active
sources: ["project roadmap (internal)"]
updated: 2026-06-10
---

# Enterprise RAG Evaluation Lab

**Роль:** MVP-модуль №3 — демонстрация зрелого AI Engineering. Отличает проект от
«обычного чата с PDF».

**Что делает:** [[rag]] pipeline + строгая оценка качества retrieval и ответов.

**Sprint 2 (1 нед):** RAG Core — ingestion, chunking, embeddings, vector search, citations.
✅ done 2026-06-10 → [[rag]].
**Sprint 2.1:** RAG Eval v0 — retrieval hit rate, citation accuracy, answer groundedness;
первый eval report по sample documents. ✅ done 2026-06-10: `platform/evals`
(`workbench-evals`) — retrieval-метрики (hit rate, MRR, context precision — чистые функции),
citation accuracy ([n]-маркеры против retrieved chunks), RAG answerer (ответ строго из
контекста с citations, standard-tier), LLM-judges faithfulness/answer relevance
(judge-tier → frontier, defensive JSON-парсинг вердиктов), synthetic QA-генерация из
индекса (семя [[synthetic-eval-generator]]), отчёты в `data/eval_results/*.json` +
агрегаты и LLM-cost. API: `POST /v1/evals/rag` (inline dataset или synthetic).

**DoD:** документы загружаются/индексируются/находятся релевантные chunks; есть eval report.
**Стек:** Qdrant/pgvector, PyMuPDF, embeddings, Ragas/DeepEval/custom.

> OpenAI и Anthropic выделяют evals как обязательную часть надёжных AI-приложений,
> особенно для многошаговых агентов с tools и состоянием.

Акцент на eval lab, corrective RAG, citation accuracy, regression — чтобы не выглядеть
«чатом с PDF».

**Метрики:** retrieval hit rate 70%+/85%+, citation accuracy 70%+/85%+, context
precision/recall, faithfulness, answer relevance → [[evals]].
**Связи:** [[synthetic-eval-generator]] (датасеты), [[text-to-sql-rag-agent]].

## Sources
- `project roadmap (internal)` p. 10 (Sprint 2), стр. 19–20 (риски), стр. 22 (метрики).
