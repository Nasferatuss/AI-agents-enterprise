---
type: concept
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# Evals

Платформенный **Evaluation Engine**: datasets, scorers, judges, reports.
Eval taxonomy (Design 4): RAG, SQL, agent, tool, safety.

> OpenAI и Anthropic выделяют evals как обязательную часть надёжных AI-приложений,
> особенно для многошаговых агентов с tools и состоянием.

**Стек:** Ragas, DeepEval, promptfoo, custom harness → [[tech-stack]].

**Связанные модули:** [[rag-evaluation-lab]], [[synthetic-eval-generator]] (датасеты),
[[text-to-sql-rag-agent]]. Eval regression — часть QA (Phase 4) → [[phases-and-sprints]].

**Метрики по направлениям** см. [[kpi-and-metrics]]. Риски: стоимость API при evals,
недостоверность synthetic dataset → [[risk-register]].

## Sources
- `Дорожная карта.pdf` стр. 9–11, 14, 21–22.
