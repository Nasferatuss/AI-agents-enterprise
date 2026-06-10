.DEFAULT_GOAL := help

.PHONY: help install api test lint fmt up down ps logs ui ui-build

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

fmt: ## Format Python
	uv run ruff format .
	uv run ruff check --fix .

up: ## Start infra + API via Docker Compose
	docker compose -f infra/docker/docker-compose.yml up -d --build

down: ## Stop Docker Compose stack
	docker compose -f infra/docker/docker-compose.yml down

ps: ## Show compose services
	docker compose -f infra/docker/docker-compose.yml ps

logs: ## Tail compose logs
	docker compose -f infra/docker/docker-compose.yml logs -f --tail=100

ui: ## Run Next.js demo console (dev)
	cd ui/web && npm run dev

ui-build: ## Production build of demo console
	cd ui/web && npm run build
