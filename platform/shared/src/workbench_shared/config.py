"""Central platform configuration.

Every platform service and demo app reads settings from here — a single
env-driven source of truth (prefix ``WB_``), never ad-hoc ``os.environ`` reads.
"""

from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WB_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000"]  # demo console (ui/web)
    # Optional shared-secret gate on workflow approve/reject (governance control).
    # Empty = open (local demo); set WB_APPROVAL_TOKEN to require an X-Approval-Token header.
    approval_token: str = ""
    # Optional gateway API auth + rate limit (off by default so the local demo is open).
    # WB_API_KEY: when set, /v1/* requires a matching X-API-Key header.
    # WB_RATE_LIMIT_PER_MIN: when > 0, cap POST /v1/* per client IP per minute.
    api_key: str = ""
    rate_limit_per_min: int = 0

    # Storage
    postgres_dsn: str = "postgresql://workbench:workbench@localhost:5432/workbench"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"

    # Background jobs (async run model). "inprocess" (default) runs jobs as asyncio
    # tasks in the gateway; "redis" enqueues to Redis for a separate worker process
    # (`python -m workbench_gateway.worker`) — the horizontally-scalable path.
    job_backend: Literal["inprocess", "redis"] = "inprocess"

    # Model routing (ADR-003 hybrid local/API split + ADR-008 router).
    # API keys use standard env names (ANTHROPIC_API_KEY, OPENAI_API_KEY,
    # DEEPSEEK_API_KEY, MOONSHOT_API_KEY, MIMO_API_KEY) — see workbench_runtime.providers.
    local_llm_base_url: str = "http://localhost:11434"  # Ollama on the GPU box (LAN IP in .env)
    local_llm_model: str = "qwen2.5:3b-instruct"
    deepseek_model: str = "deepseek-chat"
    kimi_model: str = "kimi-k2-0905-preview"
    anthropic_model: str = "claude-opus-4-8"
    anthropic_small_model: str = "claude-haiku-4-5"
    openai_model: str = "gpt-5.1"
    mimo_base_url: str = ""  # set to the OpenAI-compatible endpoint to enable the mimo provider
    mimo_model: str = ""
    # Prepend local to the standard-tier chain (turn on after pulling a 14B+ model on the 4090)
    route_standard_via_local: bool = False

    # RAG Core (Sprint 2): embeddings run locally per ADR-003 (Ollama on the GPU box).
    # "hash" is a deterministic non-semantic fallback for keyless/GPU-less dev.
    embeddings_backend: Literal["ollama", "hash"] = "ollama"
    embedding_model: str = "nomic-embed-text"

    # Evaluation Engine (Sprint 2.1)
    eval_results_dir: str = "data/eval_results"

    # Text-to-SQL app (Sprint 3, ADR-004): sandbox BI database. SQLite file is
    # auto-created with sample retail data and opened read-only; for Postgres
    # point this at a sandbox DB with a read-only user.
    bi_database_url: str = "sqlite:///examples/bi/retail.db"

    # Tool Gateway MCP client (ADR-005). When set to a shell-style command
    # (e.g. "python -m workbench_toolgateway.mcp_server" or "uvx mcp-server-fetch"),
    # the deep-research agent sources its tools from a real MCP server over stdio
    # instead of the in-process corpus connectors. Empty = current behavior.
    mcp_server_command: str = ""

    # Deep-research live web (apps/deep_research). When true (WB_RESEARCH_LIVE_WEB=true)
    # and no MCP server is configured, the agent's web_search/fetch hit the real
    # internet (DuckDuckGo + httpx page fetch) instead of the in-process corpus,
    # falling back to the corpus when the network fails. Off = current behavior.
    research_live_web: bool = False

    # Observability trace store (Sprint 5, ADR-006). Defaults to a local sqlite
    # file so traces work without Docker; `make up` overrides this to Postgres
    # (postgresql+asyncpg://…). Always an async SQLAlchemy URL.
    trace_db_url: str = "sqlite+aiosqlite:///data/traces.db"


@lru_cache
def get_settings() -> Settings:
    # Provider API keys (ANTHROPIC_API_KEY, …) are read from os.environ, not from
    # Settings fields — pull .env into the environment first. Never overrides
    # variables already set in the shell.
    load_dotenv()
    return Settings()
