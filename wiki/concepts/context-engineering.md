---
type: concept
sources: ["Дорожная карта.pdf"]
updated: 2026-06-10
---

# Context Engineering

Платформенный **Context Engine**: context policies, summarization, compression,
memory retrieval. Управляет контекстом агента.

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

**Связи:** [[rag]] (retrieval), [[agent-observability-console]] (сохранённый контекст в trace),
Agent Runtime · [[adr-008-model-router-design]]. См. [[phases-and-sprints]].

## Sources
- `Дорожная карта.pdf` стр. 2, 10.
- Реализация: `platform/runtime` (Sprint 1.1, 2026-06-10).
