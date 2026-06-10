---
type: decision
status: active
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# ADR-002 — MVP = ядро + 3 модуля, не все 10

**Решение:** MVP включает ядро платформы + **3** модуля высокой глубины, а не все 10
одинаково глубоко.

**MVP-набор** (лучше всего демонстрирует архитектурный уровень):
1. [[enterprise-workflow-orchestrator]] — ядро.
2. [[text-to-sql-rag-agent]] — самый понятный enterprise use case.
3. [[rag-evaluation-lab]] — демонстрация зрелого AI Engineering.
4. [[agent-observability-console]] — сквозной proof of production thinking.

**Обоснование:** попытка сделать все 10 модулей одинаково глубоко почти гарантированно
размывает качество. Правильная стратегия — MVP (ядро + 3) → Portfolio (10) → Showcase.

**Следствие:** остальные 6 модулей — через phased rollout (Sprints 6–9). Жёсткий
release plan: MVP публично за 8–10 недель → [[phases-and-sprints]] · [[risk-register]].

## Sources
- `Дорожная карта.pdf` стр. 2, 7, 23–24.
