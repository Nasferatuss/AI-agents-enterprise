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

    # Storage
    postgres_dsn: str = "postgresql://workbench:workbench@localhost:5432/workbench"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"

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


@lru_cache
def get_settings() -> Settings:
    # Provider API keys (ANTHROPIC_API_KEY, …) are read from os.environ, not from
    # Settings fields — pull .env into the environment first. Never overrides
    # variables already set in the shell.
    load_dotenv()
    return Settings()
