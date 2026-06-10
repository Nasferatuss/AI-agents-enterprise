---
type: concept
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# Observability

Платформенный **Observability Layer**: traces, logs, token usage, latency, cost,
failure taxonomy. Сквозной MVP-приоритет.

**Trace model:** run → step → tool call → model call → error → cost (+ latency, tokens).
Начинать с custom schema → [[adr-006-custom-trace-schema]].

**Стек:** OpenTelemetry, Langfuse, structured logs, custom trace viewer → [[tech-stack]].

**Модуль-витрина:** [[agent-observability-console]]. Питает [[incident-response-agent]]
(failed traces → RCA).

**Метрика:** runs with full trace 100% → [[kpi-and-metrics]].

## Sources
- `Дорожная карта.pdf` стр. 3, 12.
