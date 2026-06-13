---
type: concept
sources: ["Дорожная карта.pdf", "OpenAI — A practical guide to building agents"]
updated: 2026-06-13
---

# Governance

Платформенный **Policy / Governance Engine**: guardrails, allow/deny rules, PII checks,
approval gates, audit log. Policy engine на YAML/JSON rules.

McKinsey (2026) выделяет agentic AI trust, governance и risk controls как ключевые
барьеры масштабирования AI в бизнесе — поэтому governance это реальные gates, а не формальность
(риск «governance выглядит формально» → [[risk-register]]).

## Guardrails как layered defense (OpenAI — practical guide)

OpenAI трактует guardrails как **многослойную защиту**: один guardrail недостаточен — несколько
специализированных вместе дают resilient-агента. В референс-схеме они комбинируют LLM-based
guardrails, rules-based (regex) и OpenAI Moderation API для проверки входов. Named типы
(прямо из источника):

- **Relevance classifier** — держит ответы в scope, флагит off-topic запросы.
- **Safety classifier** — детектит unsafe inputs (jailbreaks / prompt injections), пытающиеся
  эксплуатировать систему. (Наш security-review + adversarial SQL-suite — это эта линия.)
- **PII filter** — вычищает model output на предмет утечки personally identifiable information.
- **Moderation** — флагит harmful/inappropriate input (hate speech, harassment, violence).
- **Tool safeguards** — оценка риска **каждого tool**: рейтинг low/medium/high по факторам
  read-only vs write, reversibility, требуемые permissions, financial impact. Рейтинг триггерит
  автоматику: пауза на guardrail-проверку перед high-risk функцией или эскалация человеку.
  Прямо обосновывает наш tool allowlist → [[adr-005-mcp-security-boundary]] и [[mcp-tool-use]].
- **Rules-based protections** — детерминированные меры: blocklists, input length limits,
  regex-фильтры (против prohibited terms, SQL injection). Ср. sqlglot-гарды
  → [[adr-004-readonly-sql-safety]].
- **Output validation** — проверка, что ответ соответствует brand values (prompt engineering +
  content checks).

**Human intervention** OpenAI называет критическим safeguard. Два триггера эскалации человеку:
(1) превышение **failure thresholds** (лимиты на retries/actions агента); (2) **high-risk actions**
(sensitive/irreversible/high-stakes — отмена заказов, крупные refunds, платежи). Это ровно наш
HITL approval-gate в [[enterprise-workflow-orchestrator]] → [[adr-007-predictable-orchestration]].
Эвристика построения guardrails: сначала data privacy + content safety, затем добавлять новые
по реальным edge cases и failures, оптимизируя security и UX по мере эволюции агента.

**Конкретные gates по модулям:**
- [[adr-004-readonly-sql-safety]] — read-only, allowlist таблиц, sandbox DB.
- [[adr-005-mcp-security-boundary]] — tool allowlist, permissions, audit, no shell.
- [[adr-007-predictable-orchestration]] — human approval перед risky action.
- [[compliance-risk-reviewer]] — risk report по policy rules.

**Метрики:** risky actions behind approval gate 100%, PII detection rate, approval
compliance, blocked unsafe tool calls → [[kpi-and-metrics]].
QA: Security & Governance QA, incl. prompt injection cases → [[phases-and-sprints]].

## Реализовано (частично)

**Approval gates + audit (Sprint 4.1, 2026-06-13)** — первый governance-механизм в коде:
human-in-the-loop approval перед risky action в [[enterprise-workflow-orchestrator]]
(`requires_approval` на шаге → pause → approve/reject → `run.approvals` audit log).
Полный Policy/Governance Engine (allowlist tools, PII checks, approval policies на уровне
платформы) — отдельный слой, Design 6 / позже.

## Sources
- `Дорожная карта.pdf` стр. 1, 3, 9, 13, 15, 20–22.
- OpenAI — *A practical guide to building agents*,
  https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/
  (PDF: cdn.openai.com/...), секция Guardrails — layered defense; named типы (relevance classifier,
  safety classifier, PII filter, moderation, tool safeguards с risk-рейтингом low/medium/high,
  rules-based protections, output validation); plan for human intervention (failure thresholds,
  high-risk actions); эвристика построения guardrails.
