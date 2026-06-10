---
type: concept
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# Context Engineering

Платформенный **Context Engine**: context policies, summarization, compression,
memory retrieval. Управляет контекстом агента.

**Sprint 1.1 (Context Engine v0):** context builder — system prompt, retrieved chunks,
memory, task state. DoD: каждый run сохраняет использованный контекст.

**Стек:** Pydantic, PostgreSQL → [[tech-stack]].

**Связи:** [[rag]] (retrieval), [[agent-observability-console]] (сохранённый контекст в trace),
Agent Runtime. См. [[phases-and-sprints]].

## Sources
- `Дорожная карта.pdf` стр. 2, 10.
