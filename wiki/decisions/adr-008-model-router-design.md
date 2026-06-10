---
type: decision
status: active
sources: ["разговор с пользователем 2026-06-10", "Дорожная карта.pdf"]
updated: 2026-06-10
---

# ADR-008 — Model Router: свой, local-first, три cost-tier

**Контекст:** ADR-003 требует hybrid local/API split. Доступные ресурсы (2026-06-10):
ключи **Anthropic, OpenAI, DeepSeek, Kimi (Moonshot), Mimo**; локальная машина с
**RTX 4090** (Ollama, скачаны Qwen2.5-3B-Instruct и Qwen3-1.7B). Пользователь предпочитает
local-first ради экономии. GPU-машина — отдельная от dev-Mac (доступ по LAN).

**Решение:** свой тонкий router (`platform/runtime`, ~150 строк) вместо LiteLLM.

1. **Один протокол почти для всех**: OpenAI, DeepSeek, Kimi, Ollama, Mimo говорят
   OpenAI-compatible `/chat/completions` → один httpx-клиент. **Anthropic — через
   официальный SDK** (typed errors, retries, adaptive thinking для complex/judge).
2. **Tier-цепочки по complexity** с graceful fallback (unreachable/5xx/429 → следующий):
   | Complexity | Цепочка |
   |---|---|
   | `simple` | local → deepseek → kimi → claude-haiku-4-5 |
   | `standard` | [local]* → deepseek → kimi → frontier |
   | `complex` / `judge` | claude-opus-4-8 (adaptive thinking) → openai |
   \* local включается флагом `WB_ROUTE_STANDARD_VIA_LOCAL` после докачки 14B+ модели.
3. **Провайдер включён ⇔ ключ задан** (стандартные env: `ANTHROPIC_API_KEY`, …).
   Локальный — всегда включён, но падает в fallback, если 4090-машина выключена.
4. **Cost-телеметрия на каждый вызов**: tokens, cost (прайс-таблица `pricing.py`,
   Anthropic verified, остальные approximate), latency, fallbacks → structlog,
   позже — в trace-схему [[observability]].

**Обоснование «свой, не LiteLLM»:** портфолио-проект демонстрирует engineering;
полный контроль routing-политики; нулевые лишние зависимости; LiteLLM остаётся
опцией, если протоколы разойдутся.

**Рекомендация по локальным моделям:** 3B/1.7B — только simple-tier (classification,
extraction). На 24GB VRAM 4090 стоит докачать **Qwen3-14B** (или Qwen3-30B-A3B quantized) —
тогда standard-tier тоже станет бесплатным.

**Связи:** [[adr-003-local-api-model-split]] · [[tech-stack]] · [[service-oriented-core]] (Agent Runtime)

## Sources
- Пользователь, 2026-06-10: доступные ключи, железо, предпочтение local-first.
- `Дорожная карта.pdf` стр. 3–4, 8 (model-router, hybrid split).
