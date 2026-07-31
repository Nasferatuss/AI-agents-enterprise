---
type: decision
status: active
sources: ["project roadmap (internal)"]
updated: 2026-06-07
---

# ADR-006 — Custom trace schema, не LangSmith-клон

**Контекст:** [[observability]] легко может «съесть» слишком много времени (риск Med/Med).

**Решение:** начать с собственной минимальной **trace schema**, не строить
полноценный LangSmith-клон.

**Trace model:** run → step → tool call → model call → error → cost
(+ latency, token usage).

**Обоснование:** observability — сквозной MVP-приоритет ([[agent-observability-console]]),
но ценность в proof of production thinking, а не в воспроизведении целого продукта.

**Связи:** Design 5 + Sprint 5 — runs with full trace 100%.

## Sources
- `project roadmap (internal)` p. 12, 20.
