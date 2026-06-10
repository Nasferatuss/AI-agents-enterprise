---
type: decision
status: active
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# ADR-003 — Hybrid local/API model split (RTX 4070 8GB)

**Контекст:** доступна RTX 4070 8GB. Нельзя строить roadmap вокруг тяжёлых локальных
LLM (30B/70B) без серьёзных компромиссов.

**Решение:** hybrid-режим через **model-router**:
- **локально:** embeddings, reranker, 7B/8B quantized LLM, простые агенты;
- **через внешний API:** сложный reasoning, judge/eval, computer-use;
- архитектура переключает модели через единый model-router (LiteLLM или свой).

**Обоснование:** реалистичность под железо + контроль стоимости API
(batch evals, caching, маленькие judge-модели) → [[risk-register]].

**Связи:** [[tech-stack]], Phase 1 Discovery 4 (feasibility) → [[phases-and-sprints]].

## Sources
- `Дорожная карта.pdf` стр. 3–4, 8, 19.
