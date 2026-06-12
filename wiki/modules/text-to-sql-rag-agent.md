---
type: module
status: active
sources: ["Дорожная карта.pdf"]
updated: 2026-06-12
---

# Text-to-SQL + RAG BI Agent

**Роль:** MVP-модуль №2 — самый понятный enterprise use case.

**Что делает:** бизнес-вопрос → SQL → результат → объяснение. Schema explorer,
SQL generation, **SQL validation**, safe query execution, explanation.

**Sprint 3 (1 нед):** SQL Agent MVP. ✅ done 2026-06-12: `apps/text2sql`
(`workbench-app-text2sql`) — первое «тонкое приложение» поверх platform:
- **safe_sql** (все 5 уровней [[adr-004-readonly-sql-safety]]): sqlglot-парсер
  (одна statement, только SELECT/CTE/UNION, запрещённые узлы где угодно в дереве —
  ловит и `WITH x AS (DELETE…)`); allowlist таблиц (CTE-имена исключаются);
  принудительный LIMIT 200 (инъекция/срезание); sandbox sample DB (retail:
  customers/products/orders/order_items, детерминированная генерация); SQLite
  открывается `mode=ro` — defense in depth, запись блокируется даже мимо валидации.
- **Агент**: schema reflection → детерминированное описание в instructions
  (prompt caching), tool `run_sql` (JSON: sql/columns/rows/row_count), отклонённый
  SQL возвращается модели как is_error — агент восстанавливается.
- **API**: `GET /v1/apps/text2sql/schema`, `POST /v1/apps/text2sql/ask` →
  `{answer, sql_calls[], run}` — полный путь вопрос → SQL → результат (DoD под UI).

**Sprint 3.1:** BI UI — таблица результата, generated SQL, reasoning trace,
chart placeholder. — next

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
