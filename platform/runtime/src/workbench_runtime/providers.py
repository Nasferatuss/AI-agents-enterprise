"""Provider registry (ADR-008).

A provider is enabled when its API key is present in the environment (the local
Ollama endpoint needs no key). Standard env var names are used on purpose —
ANTHROPIC_API_KEY etc. — so SDKs and CLIs pick them up too. Model choices are
env-tunable via WB_* settings (see workbench_shared.config).
"""

import os
from dataclasses import dataclass, field
from typing import Literal

from workbench_shared.config import get_settings

ProviderKind = Literal["anthropic", "openai_compatible"]


@dataclass(frozen=True)
class Provider:
    name: str
    kind: ProviderKind
    base_url: str  # for anthropic kind: "" (SDK default)
    api_key_env: str  # "" → no key required (local)
    models: dict[str, str] = field(default_factory=dict)  # role → model id

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) if self.api_key_env else None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key) if self.api_key_env else True


def build_registry() -> dict[str, Provider]:
    s = get_settings()
    providers = [
        Provider(
            name="local",
            kind="openai_compatible",
            base_url=f"{s.local_llm_base_url.rstrip('/')}/v1",  # Ollama's OpenAI-compatible API
            api_key_env="",
            models={"default": s.local_llm_model},
        ),
        Provider(
            name="deepseek",
            kind="openai_compatible",
            base_url="https://api.deepseek.com/v1",
            api_key_env="DEEPSEEK_API_KEY",
            models={"default": s.deepseek_model},
        ),
        Provider(
            name="kimi",
            kind="openai_compatible",
            base_url="https://api.moonshot.ai/v1",
            api_key_env="MOONSHOT_API_KEY",
            models={"default": s.kimi_model},
        ),
        Provider(
            name="anthropic",
            kind="anthropic",
            base_url="",
            api_key_env="ANTHROPIC_API_KEY",
            models={"default": s.anthropic_model, "small": s.anthropic_small_model},
        ),
        Provider(
            name="openai",
            kind="openai_compatible",
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
            models={"default": s.openai_model},
        ),
    ]
    # Mimo: OpenAI-compatible, but base_url differs per deployment — opt-in via env
    if s.mimo_base_url:
        providers.append(
            Provider(
                name="mimo",
                kind="openai_compatible",
                base_url=s.mimo_base_url,
                api_key_env="MIMO_API_KEY",
                models={"default": s.mimo_model},
            )
        )
    return {p.name: p for p in providers}
