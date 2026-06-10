---
type: concept
sources: ["Дорожная карта.pdf"]
updated: 2026-06-10
---

# Evals

Платформенный **Evaluation Engine**: datasets, scorers, judges, reports.
Eval taxonomy (Design 4): RAG, SQL, agent, tool, safety.

> OpenAI и Anthropic выделяют evals как обязательную часть надёжных AI-приложений,
> особенно для многошаговых агентов с tools и состоянием.

**Evaluation Engine v0 — реализован (Sprint 2.1, 2026-06-10):** `platform/evals` —
датасеты (QAExample/EvalDataset), retrieval-метрики без LLM, citation accuracy,
LLM-judges (faithfulness, answer relevance; complexity=judge → frontier-tier по
[[adr-008-model-router-design]]), synthetic QA из индекса, персистентные отчёты
(`data/eval_results/`). Подробности → [[rag-evaluation-lab]].

**Стек:** custom harness (v0, сделан); Ragas/DeepEval/promptfoo — опционально позже → [[tech-stack]].

**Связанные модули:** [[rag-evaluation-lab]], [[synthetic-eval-generator]] (датасеты),
[[text-to-sql-rag-agent]]. Eval regression — часть QA (Phase 4) → [[phases-and-sprints]].

**Метрики по направлениям** см. [[kpi-and-metrics]]. Риски: стоимость API при evals,
недостоверность synthetic dataset → [[risk-register]].

## Sources
- `Дорожная карта.pdf` стр. 9–11, 14, 21–22.
