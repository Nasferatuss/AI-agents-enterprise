---
type: module
status: active
sources: ["Дорожная карта.pdf"]
updated: 2026-06-13
---

# Guarded Computer-Use QA Agent

**Роль:** модуль №8 (post-MVP). Концепция → [[computer-use]].

**Что делает:** смотрит UI → планирует действия → выполняет через Playwright → пишет QA/bug report.

**Sprint 8 — Legacy UI Sandbox ✅ done 2026-06-13:** `apps/computer_use_qa`
(`workbench-app-cua`) — детерминированный «legacy CRM» как state machine (login→dashboard→
customer_form→success). `observe()` отдаёт структурный экран (accessibility-tree-style
«скриншот» + text-render), `act()` применяет click/type. **Два бага заложены специально**:
BUG-1 (validation) форма принимает невалидный email; BUG-2 (content) опечатка в greeting
(«Welcom»).

**Sprint 8.1 — Computer-Use QA Agent ✅ done 2026-06-13:** агент водит sandbox **только
через Tool Gateway** ([[adr-005-mcp-security-boundary]]): action space = {observe, click, type},
allowlisted + audited («guarded» — нельзя сделать ничего, чего UI не показывает; никакого
Playwright/произвольных действий). Scenario-runner прогоняет 5 сценариев → QAReport
(pass/fail по сценарию, **bug report**, action-trace = gateway audit). 3 проходят (happy-path
+ error recovery), 2 падают → находят оба заложенных бага. LLM пишет только narrative
(deterministic findings, как в [[compliance-risk-reviewer]]). API `GET /v1/apps/cua/{scenarios,
screen}`, `POST /v1/apps/cua/run`, UI `/qa` (рендер legacy-формы + bug report).

**DoD выполнен:** агент проходит 2–3 сценария, есть bug report (+ action trace).

**Real Playwright (hardening, 2026-06-13):** виртуальный state machine больше не
единственный backend. `playwright_sandbox.py` водит **настоящий headless chromium**
по bundled `legacy_ui.html` за тем же контрактом `observe/click/type`, возвращая те же
`Screen`/`Element` объекты; `run_qa_playwright()` прогоняет те же сценарии через тот же
generic `_run_scenario` — оба заложенных бага находятся **через реальный браузер**.
Виртуальный UI остаётся быстрым default'ом (детерминирован, без браузера); browser-e2e
вынесен в отдельный CI-job (`pytest -m playwright`, `make e2e`) и deselect'ится по умолчанию,
поэтому `make test` не требует chromium. Контракт не поменялся — ровно та подстановка
«Playwright за тем же action-интерфейсом», что закладывалась в v0.

**Риск:** нестабильность агента (high) → controlled legacy UI sandbox, Playwright traces,
retries.

> OpenAI описывает computer-use как работу модели с UI; Anthropic называет это
> следующим frontier-направлением.

**Метрики:** scenario completion, action accuracy, recovery after UI error, bug report usefulness.
**Связи:** [[evals]], [[agent-observability-console]].

## Sources
- `Дорожная карта.pdf` стр. 13–14 (Sprint 8).
