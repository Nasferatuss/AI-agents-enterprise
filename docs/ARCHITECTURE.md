# Architecture

Карта того, как устроен Enterprise AI Agent Workbench: слои, как проходит запрос,
где живут durability и security. Для глубины решений — ADR'ы в
[`wiki/decisions/`](../wiki/decisions/); для запуска — [`README.md`](../README.md).

## Принцип

**Детерминированное ядро, LLM только пишет нарратив.** Оценки, verdict'ы, классификация
и guard-решения считаются кодом; модель лишь объясняет результат человеческим языком. Это
делает агентов аудируемыми — требование enterprise-контекста.

## Слои

`uv` workspace monorepo из двух половин:

- **`platform/`** — переиспользуемое ядро (сервисы).
- **`apps/`** — тонкие demo-приложения поверх ядра (FastAPI-роутер + agent на каждое).

**Железное правило (ADR-001):** `apps` зависят от `platform`, но **никогда друг от друга**.
Граф зависимостей однонаправленный — ни один `apps/X` не импортирует `apps/Y`. Общие
способности (SQL guard, schema reflection, BI engine, governed web) вынесены в
`platform/capabilities`, чтобы убрать app→app coupling.

### `platform/` — ядро

| Пакет | Модуль | Ответственность |
|---|---|---|
| `platform/shared` | `workbench_shared` | Конфиг (`WB_*`), logging, SSRF-guard (`netguard`), базовые схемы |
| `platform/gateway` | `workbench_gateway` | FastAPI app factory, middleware (auth/rate/headers), монтаж роутеров, worker entrypoint |
| `platform/runtime` | `workbench_runtime` | Model router (цепочки + fallback), agent loop, context engine, провайдер-клиенты |
| `platform/orchestrator` | `workbench_orchestrator` | Детерминированная workflow state-machine + HITL gates, durable run registry |
| `platform/observability` | `workbench_observability` | Async trace store (`traces` + `agent_runs`), `safe_record`, sweeper |
| `platform/jobs` | `workbench_jobs` | Distributed job queue: in-process + Redis backends, at-least-once |
| `platform/capabilities` | `workbench_capabilities` | Read-only SQL guard, schema reflection, BI engine, governed web |
| `platform/toolgateway` | `workbench_toolgateway` | Tool registry + per-call allowlist + audit log, MCP client/server |
| `platform/rag` | `workbench_rag` | RAG pipeline: chunking → embeddings → Qdrant → hybrid search (dense+BM25, RRF) |
| `platform/evals` | `workbench_evals` | RAG eval: generate → answer → LLM-judge → metrics → regression gate |

### `apps/` — demo

`text2sql` · `autonomous_agent` ⭐ · `deep_research` ⭐ · `computer_use_qa` ⭐ ·
`compliance_reviewer` · `incident_response` · `process_investigator`
(⭐ — три флагмана: реальные web/browser/autonomous, не стабы).

## Жизненный цикл синхронного запроса

Пример: `POST /v1/apps/text2sql/ask`.

```
HTTP
 │
 ▼  platform/gateway/app.py — middleware (исполняются в порядке):
 │    SecurityHeaders → RateLimit → ApiKey → CORS         (auth/rate — no-op по умолчанию)
 ▼  apps/text2sql/api.py: ask()
 │    build_agent(engine) → Agent с run_sql tool + schema в instructions
 ▼  platform/runtime/agent.py: run_agent() — цикл до max_steps:
 │    maybe_compact(transcript) → router.step() → если есть tool_calls: execute_tool()
 ▼  platform/runtime/router.py: step()
 │    chain(complexity) → пропустить cooldown'нутых → попытка → при ошибке fallback на следующего
 ▼  platform/capabilities/sql_guard.py: execute_sql()
 │    validate_sql() [5 уровней] → выполнить в read-only коннекте
 ▼  platform/runtime/tracing.py: record_agent_run()
      _scrub_payload() → safe_record()  (best-effort — сбой БД не роняет запрос)
```

## Durable / async runs (ADR-010)

Дорогой run (autonomous — минуты под frontier-моделью) нельзя держать в одном HTTP-запросе:
LB с таймаутом 30–60s оборвёт. Модель — submit → 202 → фон → poll:

- `POST /v1/apps/autonomous/runs` → `create_run` (INSERT в `agent_runs`) → `enqueue(Job)` → **202** с `run_id`.
- Handler `_execute_run` исполняет в фоне, бьёт heartbeat (`touch_run`), пишет терминальный статус.
- `GET /v1/apps/autonomous/runs/{id}` — поллит статус из durable store (читаемо с любой реплики).

**HITL переживает рестарт:** orchestrator-registry — write-through cache + load-on-miss;
run, замерший на approval-gate, регидрируется из БД (`WorkflowRun.model_validate(payload)`).

## Distributed job queue (`platform/jobs/queue.py`)

Seam между «submit» и «execute». Бэкенд по `WB_JOB_BACKEND`:

- **`inprocess`** (default) — handler как asyncio task в gateway. Single-replica.
- **`redis`** — `LPUSH` в список, отдельный worker (`python -m workbench_gateway.worker`)
  консьюмит. Горизонтально масштабируемый путь.

**Гарантия — at-least-once + effectively-once:** `BLMOVE` main→processing (атомарно) → dispatch
→ `LREM` ack только после исполнения; `reclaim()` на старте возвращает осиротевшие job;
handler идемпотентен (пропускает уже терминальный run). Полностью — [`docs/distributed.md`](distributed.md).

**Crash-recovery слои:** reclaim (crash между pop и ack) · reconciler (рестарт с
`pending`/`running`) · heartbeat+sweeper (зависший воркер) · `UNIQUE(kind, idempotency_key)`
(конкурентные дубли).

## Security boundary

Главная угроза — prompt-injected модель, эмитящая опасный tool call. Boundary живёт **в коде
guard'ов**, не в промпте:

- **SSRF** (`platform/shared/netguard.py`) — `assert_public_url` резолвит DNS и требует, чтобы
  каждый IP был globally routable (блок private/loopback/link-local/metadata/CGNAT/IPv4-mapped);
  `safe_get` ре-валидирует каждый redirect hop.
- **SQL** (`platform/capabilities/sql_guard.py`) — 5 уровней: sqlglot AST · function denylist ·
  table allowlist · forced LIMIT · read-only коннект (настоящий boundary).
- **File sandbox** (autonomous `tools.py`) — reject абсолютных путей, `..`-traversal,
  symlink-escape; 100KB write cap.
- **Gateway** (`gateway/security.py`) — prod fail-fast без `WB_API_KEY`/`WB_APPROVAL_TOKEN`/
  явного CORS; опциональные API-key gate и rate-limit; security headers всегда.
- **Tool Gateway** (`platform/toolgateway/gateway.py`) — registry + per-call allowlist; denied
  вызов логируется и не исполняется.

Известные ограничения и threat model — [`docs/security.md`](security.md).

## Observability

Своя trace-schema (не OpenTelemetry) ради доменной семантики агента: tier-решение роутера,
allowed/denied tool calls, cost на запуск, provider-attempts при fallback. Таблица `traces`
(`kind/name/status/latency_ms/cost_usd/tokens/num_steps/error/payload`). Запись **best-effort**
(`safe_record` в try/except) — телеметрия никогда не на критическом пути; сырые `rows`
вырезаются из payload (`_scrub_payload`).

## Конфигурация

Все настройки — env-переменные с префиксом `WB_` (`platform/shared/config.py`,
`pydantic_settings`). Ключевые: `WB_ENV` (`prod` → fail-fast security), `WB_API_KEY`,
`WB_JOB_BACKEND`, `WB_TRACE_DB_URL`, `WB_RUN_STUCK_TTL_S`. Провайдерские ключи
(`ANTHROPIC_API_KEY` и т.п.) читаются напрямую из env. Полный список — в `config.py`.

## Где смотреть (порядок для нового разработчика)

1. `platform/gateway/app.py` — composition root (все middleware и роутеры разом).
2. `apps/text2sql/api.py` → `platform/runtime/agent.py` → `router.py` — путь синхронного запроса.
3. `apps/autonomous_agent/api.py` + `observability/runs.py` — async/durable модель.
4. `platform/jobs/queue.py` + `docs/distributed.md` — delivery guarantees.
5. `netguard.py` + `capabilities/sql_guard.py` — security boundary.
6. `wiki/decisions/` — ADR'ы (*почему*): 001 (core), 008 (router), 010 (durable runs),
   004 (SQL safety), 006 (trace schema).

`apps/*/api.py` — «что делает модуль»; `platform/*` — «как»; ADR'ы — «почему»; тесты рядом
с кодом — исполняемая спецификация поведения.
