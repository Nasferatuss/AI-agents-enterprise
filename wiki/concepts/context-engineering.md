---
type: concept
sources: ["project roadmap (internal)", "Anthropic — Building effective agents", "OpenAI — A practical guide to building agents"]
updated: 2026-06-13
---

# Context Engineering

Платформенный **Context Engine**: context policies, summarization, compression,
memory retrieval. Управляет контекстом агента.

## Augmented LLM как базовый блок (Anthropic)

Anthropic в *Building effective agents* называет **augmented LLM** фундаментальным
строительным блоком любого агента: модель + **retrieval + tools + memory**. Эти три
augmentation'а — ровно те слоты, что Context Engine собирает в system prompt ниже
(`<memory>`, `<retrieved_context>`, и tools через [[mcp-tool-use]]). Главный принцип
статьи — **«keep it simple»**: добавлять контекст и сложность только когда выигрыш доказуем,
мерить cost/latency-tradeoffs. Полное разбиение workflows vs agents и пять паттернов
(prompt chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer) —
в [[mcp-tool-use]]; компакция контекста здесь поддерживает любой из них.

## Foundations: model + instructions (OpenAI)

OpenAI в *practical guide* сводит агента к трём компонентам: **Model**, **Tools**
(→ [[mcp-tool-use]]), **Instructions**. Два из них — наша зона context engineering:

- **Selecting models.** Не каждая задача требует самой умной модели: простой retrieval или
  intent-classification может взять меньшую/быструю модель, а решения вроде approve refund —
  более capable. Рекомендуемый подход: прототип на самой capable модели для baseline → потом
  подменять на меньшие, где результат остаётся приемлемым. Принципы: (1) выставить evals для
  baseline → [[evals]]; (2) бить в accuracy-target лучшими доступными моделями; (3) оптимизировать
  cost/latency, заменяя большие модели меньшими. Это прямо обосновывает наш
  [[adr-008-model-router-design]] (local → cheap → frontier).
- **Configuring instructions.** Best practices: переиспользовать существующие документы
  (SOP, support-скрипты, policy) как источник routines; промптить агента **разбивать задачи**
  на мелкие шаги; **определять чёткие действия** (каждый шаг = конкретный action/output);
  **ловить edge cases** (ветвления при неполном вводе/неожиданном вопросе). Это инструкционная
  часть нашего system prompt (`<instructions>`-слот ниже). Совет: одна гибкая base-prompt с
  policy-переменными вместо множества отдельных промптов — проще maintenance и eval.

## Context Engine v0 — реализован (Sprint 1.1, 2026-06-10)

Живёт в `platform/runtime/src/workbench_runtime/context.py` (выделение в отдельный
`platform/context` — когда появятся RAG retrieval и persistent memory; сейчас это
создало бы циклическую зависимость от типов transcript).

1. **Context builder** — `ContextEngine.build()`: system prompt собирается из
   упорядоченных частей `<instructions>` → `<memory>` → `<retrieved_context>` →
   `<task_state>`. Стабильные части первыми — prefix остаётся кэшируемым
   (prompt caching). Пустые части пропускаются. Слоты memory/retrieved уже есть
   в сигнатуре `run_agent()` — [[rag]] подключится сюда без изменения интерфейса.
2. **Compaction** — при превышении бюджета (`ContextPolicy`: max_context_tokens,
   trigger_ratio, keep_recent_items) старые ходы суммаризируются в плотную
   `[conversation summary]`-заметку, свежие — verbatim. Суммаризация роутится с
   complexity=`simple` → **бесплатная локальная/дешёвая модель** ([[adr-008-model-router-design]]).
   Разрез никогда не отрывает tool call от его результата.
3. **DoD «каждый run сохраняет использованный контекст»** — `AgentRun.context`
   (`RunContext`): использованные части system prompt + события компакции
   (tokens до/после, сколько ходов свёрнуто, usage/cost самой суммаризации).
   Это часть trace-схемы → [[adr-006-custom-trace-schema]]; persistence в Postgres —
   со слоем трейсов (Sprint 5).

Оценка токенов — эвристика chars/4 (достаточно для бюджетирования; интерфейс
позволяет заменить на провайдерские токенизаторы).

**Стек:** Pydantic, PostgreSQL → [[tech-stack]].

**Связи:** [[rag]] (retrieval), [[mcp-tool-use]] (tools, augmented LLM, agent-паттерны),
[[evals]] (model baseline), [[agent-observability-console]] (сохранённый контекст в trace),
Agent Runtime · [[adr-008-model-router-design]].

## Sources
- `project roadmap (internal)` p. 2, 10.
- Реализация: `platform/runtime` (Sprint 1.1, 2026-06-10).
- Anthropic — *Building effective agents*, https://www.anthropic.com/research/building-effective-agents
  — augmented LLM (model + retrieval + tools + memory) как базовый блок, «keep it simple».
- OpenAI — *A practical guide to building agents*,
  https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/
  (PDF: cdn.openai.com/...) — три foundations (model/tools/instructions); selecting models
  (baseline на capable модели → downsize, evals для baseline); configuring instructions
  (existing docs, break down tasks, define clear actions, capture edge cases, base-prompt с переменными).
