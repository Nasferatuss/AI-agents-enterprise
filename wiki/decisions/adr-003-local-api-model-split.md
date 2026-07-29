---
type: decision
status: active
sources: ["Дорожная карта.pdf", "разговор с пользователем 2026-06-10"]
updated: 2026-06-10
---

# ADR-003 — Hybrid local/API model split (RTX 4070 8GB)

> ⚠️ Противоречие: `Дорожная карта.pdf` (стр. 3–4) исходит из **RTX 4070 8GB**,
> но фактически (пользователь, 2026-06-10) GPU-машина — **RTX 4090** (24GB),
> отдельная от dev-Mac, с Ollama и моделями Qwen2.5-3B-Instruct / Qwen3-1.7B.
> 24GB позволяют 14B–30B quantized — гибрид остаётся в силе, но локальный tier
> может брать на себя больше. Реализация → [[adr-008-model-router-design]].

**Контекст:** доступна RTX 4070 8GB. Нельзя строить roadmap вокруг тяжёлых локальных
LLM (30B/70B) без серьёзных компромиссов.

**Решение:** hybrid-режим через **model-router**:
- **локально:** embeddings, reranker, 7B/8B quantized LLM, простые агенты;
- **через внешний API:** сложный reasoning, judge/eval, computer-use;
- архитектура переключает модели через единый model-router (LiteLLM или свой).

**Обоснование:** реалистичность под железо + контроль стоимости API
(batch evals, caching, маленькие judge-модели).

**Связи:** [[tech-stack]], Phase 1 Discovery 4 (feasibility).

## Sources
- `Дорожная карта.pdf` стр. 3–4, 8, 19.
