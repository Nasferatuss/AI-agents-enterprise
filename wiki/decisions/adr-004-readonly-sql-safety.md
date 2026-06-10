---
type: decision
status: active
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# ADR-004 — Read-only SQL safety

**Контекст:** [[text-to-sql-rag-agent]] может генерировать опасный SQL (риск High/High).

**Решение:** многоуровневая защита:
- только **read-only** запросы;
- **SQL parser** для валидации перед выполнением;
- **allowlist таблиц**;
- обязательный **LIMIT**;
- выполнение в **sandbox DB**.

**Обоснование:** tool connectivity к БД — серьёзная поверхность риска; нужны guardrails
на уровне execution, а не только промпта. См. [[governance]] · [[risk-register]].

## Sources
- `Дорожная карта.pdf` стр. 19 (risk register).
