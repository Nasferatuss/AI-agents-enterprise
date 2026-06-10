---
type: concept
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# Computer Use

Работа агента через UI (а не только API): смотрит экран → планирует действия → выполняет.

> OpenAI описывает computer-use как возможность модели работать с пользовательским
> интерфейсом; Anthropic называет computer use следующим frontier-направлением.

**Стек:** Playwright + screenshot/action traces; опц. computer-use API → [[tech-stack]].

**Модуль-витрина:** [[guarded-computer-use-qa-agent]] (Sprint 8) — на controlled legacy
UI sandbox с guardrails и retries (риск нестабильности → [[risk-register]]).

**Метрики:** scenario completion, action accuracy, recovery after UI error, bug report
usefulness → [[kpi-and-metrics]].

## Sources
- `Дорожная карта.pdf` стр. 4, 13–14.
