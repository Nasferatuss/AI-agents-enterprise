---
type: concept
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# Governance

Платформенный **Policy / Governance Engine**: guardrails, allow/deny rules, PII checks,
approval gates, audit log. Policy engine на YAML/JSON rules.

McKinsey (2026) выделяет agentic AI trust, governance и risk controls как ключевые
барьеры масштабирования AI в бизнесе — поэтому governance это реальные gates, а не формальность
(риск «governance выглядит формально» → [[risk-register]]).

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
