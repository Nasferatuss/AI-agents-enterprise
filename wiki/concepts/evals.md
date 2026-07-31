---
type: concept
sources: ["project roadmap (internal)", "OpenAI — Evals", "OpenAI — Graders"]
updated: 2026-06-13
---

# Evals

Платформенный **Evaluation Engine**: datasets, scorers, judges, reports.
Eval taxonomy (Design 4): RAG, SQL, agent, tool, safety.

> OpenAI и Anthropic выделяют evals как обязательную часть надёжных AI-приложений,
> особенно для многошаговых агентов с tools и состоянием.

## Структура eval (OpenAI — первоисточник)

OpenAI описывает eval из двух частей:
- **`data_source_config`** — схема тестовых данных через JSON Schema (required/optional поля).
- **`testing_criteria`** — graders, определяющие, проходит ли output. У каждого eval — свой UUID.

**Test data** загружается как JSONL: каждая строка = `item`-объект с полями и ground-truth-метками.
**Runs** исполняются асинхронно, генерируя ответ модели на каждую строку по templated-промпту
(синтаксис `{{ item.field }}`). Метрики run: `result_counts` (total/errored/failed/passed),
`per_testing_criteria_results` (pass/fail на каждый grader), `per_model_usage` (токены, вызовы).
Pass-критерий = выполнены условия grader'ов на каждом item.

## Типы graders (OpenAI — Graders, verbatim)

- **String check** — простые строковые операции (`eq` и т.п.); возвращает 0 или 1. (rule-based)
- **Text similarity** — близость output к reference: fuzzy match, BLEU, ROUGE, cosine similarity.
- **Score model** — **LLM-as-judge**: берёт input и возвращает numeric score в заданном диапазоне
  по промпту. Это ровно наши faithfulness / answer-relevance judges (judge-tier по
  [[adr-008-model-router-design]]). Ср. evaluator-optimizer-паттерн в [[mcp-tool-use]].
- **Python** — кастомный код с функцией `grade(...)`, возвращающей float.
- **Multi** — комбинирует несколько graders, агрегируя их sub-grades в общий grade.

Разделение **model graders (LLM-судьи) vs rule-based** (string check / regex / python) —
прямое обоснование нашего harness: дешёвые rule-based метрики там, где есть ground truth,
LLM-judges — там, где нужна семантическая оценка. Связь со стоимостью API при evals.

**Evaluation Engine v0 — реализован (Sprint 2.1, 2026-06-10):** `platform/evals` —
датасеты (QAExample/EvalDataset), retrieval-метрики без LLM, citation accuracy,
LLM-judges (faithfulness, answer relevance; complexity=judge → frontier-tier по
[[adr-008-model-router-design]]), synthetic QA из индекса, персистентные отчёты
(`data/eval_results/`). Подробности → [[rag-evaluation-lab]].

**Стек:** custom harness (v0, сделан); Ragas/DeepEval/promptfoo — опционально позже → [[tech-stack]].

**Связанные модули:** [[rag-evaluation-lab]], [[synthetic-eval-generator]] (датасеты),
[[text-to-sql-rag-agent]]. Eval regression — часть QA (Phase 4).

**Риски:** стоимость API при evals, недостоверность synthetic dataset.

## Sources
- `project roadmap (internal)` p. 9–11, 14, 21–22.
- OpenAI — *Evals*, https://developers.openai.com/api/docs/guides/evals — структура eval
  (`data_source_config` + `testing_criteria`, UUID), JSONL test data + ground truth, async runs,
  templated-промпты `{{ }}`, метрики (`result_counts`, `per_testing_criteria_results`, `per_model_usage`).
- OpenAI — *Graders*, https://developers.openai.com/api/docs/guides/graders — пять named типов
  (string check, text similarity, score model / LLM-as-judge, python, multi); model vs rule-based.
