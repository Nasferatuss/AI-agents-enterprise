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
   gateway) и `RedisQueue` (LPUSH/BRPOP → отдельный worker-процесс
   `python -m workbench_gateway.worker`). Выбор по `WB_JOB_BACKEND`. Handler'ы
   регистрируются по `kind`; submit кладёт `Job` в очередь, а исполняет — текущий
   процесс (inprocess) или любой worker (redis). Submit на любой реплике → исполнение
   на любом worker'е, с back-pressure через список Redis. В compose worker поднимается
   профилем `redis-jobs` (`make up-distributed`); по умолчанию демо остаётся
   in-process и не требует worker'а.

**Граница:** durable single-store + опциональный Redis-worker покрывают
горизонтальное масштабирование submit/execute и back-pressure. Чего ещё НЕ
делаем: дедлайны/ретраи-политики/scheduling/result-TTL уровня Temporal/arq — для
этого взяли бы готовый фреймворк, если появится продовый объём. Worker'ы
stateless, состояние run-ов — в durable store.

**Связи:** [[adr-006-custom-trace-schema]] · [[adr-007-predictable-orchestration]]
(HITL gates) · [[observability]] · [[service-oriented-core]] (Agent Runtime)

## Sources
- Ревью проекта 2026-06-20 (architecture): in-memory state, нет async/idempotency.
- Пользователь, 2026-06-20: «довести до 10/10 по всем пунктам».
