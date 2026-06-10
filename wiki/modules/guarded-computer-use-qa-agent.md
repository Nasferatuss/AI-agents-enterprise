---
type: module
status: draft
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# Guarded Computer-Use QA Agent

**Роль:** модуль №8 (post-MVP). Концепция → [[computer-use]].

**Что делает:** смотрит UI → планирует действия → выполняет через Playwright → пишет QA/bug report.

**Sprint 8 (1 нед):** Legacy UI Sandbox — demo legacy web UI (формы, ошибки, сценарии).
**Sprint 8.1:** Computer-Use QA Agent — проходит 2–3 сценария и пишет bug report.

**DoD:** агент проходит 2–3 сценария через Playwright; есть bug report.
**Стек:** Playwright, screenshots, guardrails, Next.js/FastAPI sandbox.

**Риск:** нестабильность агента (high) → controlled legacy UI sandbox, Playwright traces,
retries. См. [[risk-register]].

> OpenAI описывает computer-use как работу модели с UI; Anthropic называет это
> следующим frontier-направлением.

**Метрики:** scenario completion, action accuracy, recovery after UI error, bug report usefulness.
**Связи:** [[evals]], [[agent-observability-console]].

## Sources
- `Дорожная карта.pdf` стр. 13–14 (Sprint 8).
