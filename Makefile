.DEFAULT_GOAL := help

# Pass the repo-root .env to Compose for variable interpolation (host port
# overrides like WB_PG_HOST_PORT) when it exists. The api service still loads it
# as container env via its own `env_file:` directive.
COMPOSE := docker compose -f infra/docker/docker-compose.yml $(if $(wildcard .env),--env-file .env,)

.PHONY: help install api test lint fmt qa eval-regression e2e seed migrate up down ps logs ui ui-build

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Sync Python workspace (uv) and UI deps
	uv sync
	cd ui/web && npm install

api: ## Run API gateway locally with reload
	uv run uvicorn workbench_gateway.app:app --reload --port 8000

test: ## Run Python tests
	uv run pytest

lint: ## Lint Python (ruff check)
	uv run ruff check .
	uv run ruff format --check .

qa: ## Full QA gate: lint + tests (incl. eval regression + SQL injection suite)
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest -q

eval-regression: ## Run the retrieval regression gate only
	uv run pytest tests/test_eval_regression.py -q

e2e: ## Run the real-browser computer-use QA (installs chromium if needed)
	uv run playwright install chromium
	uv run pytest -m playwright -q

seed: ## Seed the trace store with sample runs (for the observability demo)
	uv run python scripts/seed_demo.py

migrate: ## Apply trace-store migrations (Postgres in the stack; reads WB_TRACE_DB_URL)
	uv run alembic -c platform/observability/alembic.ini upgrade head

fmt: ## Format Python
	uv run ruff format .
	uv run ruff check --fix .

up: ## Start infra + API via Docker Compose
	$(COMPOSE) up -d --build

down: ## Stop Docker Compose stack
	$(COMPOSE) down

ps: ## Show compose services
	$(COMPOSE) ps

logs: ## Tail compose logs
	$(COMPOSE) logs -f --tail=100

ui: ## Run Next.js demo console (dev)
	cd ui/web && npm run dev

ui-build: ## Production build of demo console
	cd ui/web && npm run build
