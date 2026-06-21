---
type: decision
status: active
sources: ["разговор с пользователем 2026-06-20", "ревью проекта 2026-06-20"]
updated: 2026-06-20
---

# ADR-010 — Durable run store + async run-модель + idempotency

**Контекст:** архитектурное ревью (2026-06-20) указало на главный production-разрыв:
всё состояние runs было **in-memory и синхронным**.
1. Orchestrator держал runs в памяти (`OrderedDict`) — пауза на human-in-the-loop
   gate (`awaiting_approval`, может длиться часами) **терялась при рестарте** gateway,
   и approve прилетал на инстанс, где run-а уже нет → HITL ломается при масштабировании.
2. Флагман (autonomous) исполнялся **синхронно внутри HTTP-запроса** (plan→act→reflect,
   минуты под frontier-моделью) → любой LB/ingress с 30–60s таймаутом обрывал run.
3. Дорогие LLM-операции **не были идемпотентны** — ретрай клиента/LB = повторный
   платный прогон.

**Решение:**

1. **Durable run store** в [[observability]] (`runs.py` + таблица `agent_runs`,
   Alembic `0002`). Generic: `id, kind, status, idempotency_key, payload(JSON),
   error, timestamps`. Переиспользует существующий async-движок trace-store
   (sqlite для dev, Postgres для стека). **Best-effort**, как trace-store: сбой БД
   деградирует к in-memory-пути, а не роняет запрос.
2. **Write-through + load-on-miss** в orchestrator-registry: in-memory кэш —
   быстрый путь; при промахе (после рестарта/на другой реплике) run
   регидрируется из БД. `WorkflowRun` — pydantic-модель, сериализуется целиком;
   определения workflow живут в коде, поэтому для resume достаточно данных run-а.
   → run, замерший на approval-gate, **переживает рестарт** (доказано тестом,
   который чистит кэш между паузой и approve).
3. **Async run-модель** для флагмана рядом с синхронным `/run`:
   `POST /runs → 202 {run_id}` исполняет в фоне (`asyncio` task) с записью в store;
   `GET /runs/{run_id}` поллит статус/результат. Долгий run больше не обязан
   уложиться в один HTTP-запрос; состояние читаемо с любой реплики.
4. **Idempotency-Key** (заголовок) на дорогих POST (`/workflows/{name}/run`,
   autonomous `/runs`): повтор с тем же ключом возвращает оригинальный run, а не
   запускает второй.

**Обоснование выбора места (observability, не новый пакет):** run-state — это
operational persistence, родственная трейсам; observability уже владеет async-движком
и Alembic-историей, и от него уже зависит orchestrator. Нулевой новый infra-слой.

5. **Job-queue с двумя бэкендами** ([[workbench-jobs]], `platform/jobs`):
   `InProcessQueue` (default, zero-config — фон через `asyncio.create_task` в самом
   gateway) и `RedisQueue` → отдельный worker-процесс
   `python -m workbench_gateway.worker`. Выбор по `WB_JOB_BACKEND`. Handler'ы
   регистрируются по `kind`; submit кладёт `Job` в очередь, а исполняет — текущий
   процесс (inprocess) или любой worker (redis). В compose worker поднимается
   профилем `redis-jobs` (`make up-distributed`); по умолчанию демо остаётся
   in-process.

6. **Гарантии доставки (post-review hardening).**
   - **Idempotency на уровне схемы**: `UNIQUE(kind, idempotency_key)` (Alembic 0003).
     `create_run` ловит `IntegrityError` и возвращает run-победителя → конкурентные
     дубли невозможны, а не только последовательные ретраи.
   - **At-least-once в RedisQueue**: `BLMOVE` main→processing (атомарно) + ack
     (`LREM`) только после исполнения; `reclaim()` на старте воркера возвращает
     осиротевшие в processing job'ы. Падение воркера mid-job → job переисполнится,
     а не потеряется.
   - **Startup reconciler** (`reconcile_runs`): на старте gateway (inprocess) или
     воркера (redis) переэнкьюивает `pending`/`running` из durable store, у которых
     есть handler — закрывает потерю in-process задач при рестарте. Paused HITL
     (`awaiting_approval`) НЕ трогается (ждёт человека, не переисполнения).
   - **Безопасность очереди**: `Job.kind`/`run_id` валидируются паттерном, `dispatch`
     исполняет только *зарегистрированные* kinds; Redis за `WB_REDIS_PASSWORD`.
   - **Heartbeat + sweeper**: handler бьёт `updated_at` (`touch_run`) пока жив;
     фоновый `run_sweeper` помечает `running` старше `WB_RUN_STUCK_TTL_S` как `failed`
     — ловит зависший (не упавший) воркер. Запускается в gateway lifespan (inprocess)
     или воркере (redis).
   - **Effectively-once**: handler идемпотентен — re-delivery уже терминального run-а
     (reclaim/reconcile) пропускается без повторной работы. Это не true exactly-once
     (run, упавший mid-flight, переисполнится), но дорогая работа над завершёнными
     run-ами не дублируется.

**Граница топологии (важно и честно):** in-process backend корректен только на
**одной** реплике gateway — его reconciler и sweeper работают per-process, поэтому N
реплик независимо переэнкьюивали бы одни и те же осиротевшие runs → до N конкурентных
переисполнений (effectively-once спасает лишь уже терминальные). Горизонтальный путь —
это Redis backend с выделенным worker'ом: reclaim/reconcile/sweep принадлежат worker'у,
а реплики gateway только submit'ят. Проверяемая демонстрация at-least-once +
effectively-once на двух worker'ах — `docs/distributed.md` + детерминированный тест
`test_two_workers_crash_midjob_reclaim_reruns_without_double_work`.

**Граница реализации:** at-least-once + reconciler + race-safe idempotency +
heartbeat/sweeper + effectively-once + **dead-letter queue с max-retries** (`Job.attempts`,
`_MAX_ATTEMPTS=5`, очередь `workbench:jobs:dead` — poison message не зацикливается, а
паркуется; глубина через `dead_letter_count()`). Чего ещё НЕ делаем (намеренно): true
exactly-once с partial-result checkpointing, per-job visibility-timeout/lease (reclaim
только просроченных, а не всего processing на старте), scheduling/result-TTL и
версионирование payload уровня Temporal/arq — для этого взяли бы готовый фреймворк, если
появится продовый объём. DLQ оставлен, т.к. это стандартная гигиена очереди, а не
durable-execution-машинерия. Worker'ы stateless, состояние run-ов — в durable store.

**Связи:** [[adr-006-custom-trace-schema]] · [[adr-007-predictable-orchestration]]
(HITL gates) · [[observability]] · [[service-oriented-core]] (Agent Runtime)

## Sources
- Ревью проекта 2026-06-20 (architecture): in-memory state, нет async/idempotency.
- Пользователь, 2026-06-20: «довести до 10/10 по всем пунктам».
