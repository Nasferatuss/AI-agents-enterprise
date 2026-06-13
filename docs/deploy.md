# Deployment (Phase 5)

## Local — full stack in Docker

```bash
make up        # postgres, qdrant, redis, api (:8000), ui (:3000)
make seed      # populate the observability/incident consoles with sample runs
open http://localhost:3000
```

`make up` builds and runs everything, including the Next.js console. The trace
store uses the Compose Postgres (`WB_TRACE_DB_URL` is overridden to the async
Postgres DSN). Provider keys / a local model are optional — read-only views work
without them; see [`setup.md`](setup.md) to wire up real models.

**Trace store schema.** On sqlite (local dev / tests) the schema is created
automatically at startup. On **Postgres** the schema is owned by Alembic — apply
migrations once:

```bash
WB_TRACE_DB_URL=postgresql+asyncpg://workbench:workbench@localhost:5432/workbench \
  make migrate
```

## Public demo — VPS / Fly.io / Render

The service is provider-agnostic and not tied to the GPU box (ADR-009): on a host
with no local model, the router's local tier simply drops out of the chain and
falls back to a cheap API (DeepSeek/Kimi) or a frontier model — no config change.

Minimal recipe (any Docker host / VPS):

```bash
# on the host
git clone https://github.com/Nasferatuss/AI-agents-enterprise && cd AI-agents-enterprise
cp .env.example .env          # add DEEPSEEK_API_KEY / ANTHROPIC_API_KEY etc.
# build the UI pointing at the public API origin:
docker compose -f infra/docker/docker-compose.yml build \
  --build-arg NEXT_PUBLIC_API_URL=https://<your-host> ui
docker compose -f infra/docker/docker-compose.yml up -d
```

Put a reverse proxy (Caddy/nginx) in front for TLS, and set
`WB_CORS_ORIGINS=["https://<your-host>"]`.

> **Before exposing to the internet**, turn on the access controls (off by default
> so the local demo stays open) — see [`security.md`](security.md):
> ```dotenv
> WB_API_KEY=<a-long-random-secret>   # require X-API-Key on every /v1/*
> WB_RATE_LIMIT_PER_MIN=60            # cap POST /v1/* per client IP
> ```
> The rate limiter is per-process; a multi-instance deployment should move the
> counter to Redis.

### Optional — real MCP tools

Deep Research can source its tools from a real MCP server over stdio instead of the
bundled corpus (same gateway allowlist + audit). Set `WB_MCP_SERVER_COMMAND` (e.g.
`python -m workbench_toolgateway.mcp_server`, or a third-party server via `uvx`) —
see [`setup.md`](setup.md) §4.1.

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs three jobs on every push/PR:
- **lint + tests** — `uv sync`, ruff lint + format check, the full pytest suite
  (incl. the eval-regression gate and the adversarial SQL suite; Playwright
  e2e is deselected here);
- **computer-use e2e (real browser)** — installs chromium and runs the
  Playwright scenarios (`pytest -m playwright`);
- **ui build** — the Next.js production build.
