---
type: module
status: draft
sources: ["Дорожная карта.pdf"]
updated: 2026-06-07
---

# Text-to-SQL + RAG BI Agent

**Роль:** MVP-модуль №2 — самый понятный enterprise use case.

**Что делает:** бизнес-вопрос → SQL → результат → объяснение. Schema explorer,
SQL generation, **SQL validation**, safe query execution, explanation.

**Sprint 3 (1 нед):** SQL Agent MVP. **Sprint 3.1:** BI UI — таблица результата,
generated SQL, reasoning trace, chart placeholder.

**DoD:** пользователь задаёт вопрос → получает SQL, результат, объяснение; UI
показывает полный путь вопрос → SQL → результат.
**Стек:** PostgreSQL, SQLAlchemy, Pydantic, Next.js, Recharts.

**Безопасность:** риск опасного SQL высокий → только **read-only**, SQL parser,
allowlist таблиц, LIMIT, sandbox DB. См. [[adr-004-readonly-sql-safety]] и [[risk-register]].

**Метрики:** valid SQL rate 80%+/90%+, execution success 75%+/90%+, schema linking
accuracy, business answer correctness → [[kpi-and-metrics]] · [[evals]].
**Связи:** [[rag]] (контекст по schema/докам), [[agent-observability-console]].

## Sources
- `Дорожная карта.pdf` стр. 11 (Sprint 3), стр. 19 (риск SQL), стр. 22 (метрики).
