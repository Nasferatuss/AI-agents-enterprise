---
type: decision
status: active
sources: ["разговор с пользователем 2026-06-10"]
updated: 2026-06-10
---

# ADR-009 — Deployment topology: сервис на Mac, GPU-машина = inference-сервер

**Контекст:** разработка идёт на Mac (репозиторий, тесты, Claude Code); отдельная
машина с RTX 4090 (24GB) в той же LAN; статического IP у GPU-машины **нет**.

**Решение:**
1. **Весь сервисный стек — на Mac**: Docker Compose (Postgres, Qdrant, Redis, api),
   Next.js console, dev-цикл. Эти компоненты CPU-лёгкие, GPU им не нужен.
2. **GPU-машина — чистый inference-сервер**: только Ollama (LLM local-tier +
   embeddings), отдаёт всё по HTTP `:11434`. Никакого кода проекта там нет.
3. **Discovery без статического IP** — по имени, не по адресу:
   - базовый вариант: **mDNS** `http://<hostname>.local:11434` (Bonjour на Mac
     резолвит из коробки; ничего ставить не надо);
   - рекомендуемый вариант: **Tailscale** на обеих машинах → стабильное имя
     `<hostname>.<tailnet>.ts.net`, работает даже вне LAN и из Docker-контейнеров.
   - ⚠️ известное ограничение: `.local` (mDNS) может не резолвиться **внутри**
     Linux-контейнеров Docker Desktop → для `make up` либо Tailscale-имя, либо
     текущий IP. Для `make api` (процесс на хосте) `.local` работает всегда.
4. **Public demo (Phase 5) — VPS без GPU**: local-tier выпадает из цепочки,
   router уходит в cheap-API ([[adr-008-model-router-design]] fallback). Свойство
   архитектуры, конфигурацию менять не нужно.

**Обоснование:** dev-цикл и код на одной машине; 4090 делает единственное, в чём
незаменима; отказ GPU-машины не валит сервис (fallback); топология не меняется
при переезде demo на VPS.

**Инструкция по настройке:** `docs/setup.md`.

**Связи:** [[adr-003-local-api-model-split]] · [[adr-008-model-router-design]] · [[tech-stack]]

## Sources
- Пользователь, 2026-06-10: подтверждение схемы; статический IP недоступен.
