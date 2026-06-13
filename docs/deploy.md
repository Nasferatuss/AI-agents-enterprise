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

> **Before exposing to the internet**, close the auth/rate-limit gaps documented
> in [`security.md`](security.md) → Known limitations (no API auth, no rate
> limiting). They are deliberately out of scope for the local MVP.

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on every push/PR: `uv sync`,
ruff lint + format check, the full pytest suite (incl. the eval-regression gate
and the adversarial SQL suite), and the Next.js production build.
