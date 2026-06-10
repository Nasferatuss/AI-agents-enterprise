"""Central platform configuration.

Every platform service and demo app reads settings from here — a single
env-driven source of truth (prefix ``WB_``), never ad-hoc ``os.environ`` reads.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WB_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"

    # Storage
    postgres_dsn: str = "postgresql://workbench:workbench@localhost:5432/workbench"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"

    # Model routing (ADR-003 hybrid local/API split) — consumed by Sprint 1 model-router
    local_llm_base_url: str = "http://localhost:11434"


@lru_cache
def get_settings() -> Settings:
    return Settings()
