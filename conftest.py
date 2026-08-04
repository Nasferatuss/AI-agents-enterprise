"""Repo-wide test isolation: hermetic trace store + hermetic provider env.

The suite is network-free and must behave identically on every machine,
regardless of what a developer keeps in their local ``.env``. Two autouse
guarantees make that true:

1. **Trace store** points at a throwaway in-memory sqlite DB so best-effort
   recording in the run routes never touches a real DB or leaves a
   ``data/traces.db`` file behind. Tests that assert on recorded traces call
   ``init_db()`` themselves (see ``platform/observability/tests/conftest.py``
   and the gateway observability test).
2. **Provider keys** are stripped, and ``load_dotenv`` is neutralised so
   ``get_settings()`` cannot re-inject ``ANTHROPIC_API_KEY`` etc. from a local
   ``.env``. Without this, the "no provider configured → 503" tests pick up a
   real key and return 200, making the result environment-dependent (green in
   CI, red on a developer laptop that has keys). A test that *wants* a provider
   sets the key itself with ``monkeypatch.setenv`` after this fixture runs.
"""

import os

import pytest

from workbench_observability import reset_engine
from workbench_shared import config as _config
from workbench_shared.config import get_settings

# Standard provider env names (see workbench_runtime.providers). Stripped from the
# environment for every test so the suite never depends on ambient credentials.
_PROVIDER_KEY_ENVS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "MOONSHOT_API_KEY",
    "MIMO_API_KEY",
)


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch):
    # Drop every WB_* value first: a real load_dotenv() anywhere (an import-time
    # call, a helper script) copies the developer's .env into os.environ for the
    # whole process, and no later monkeypatching of the loader takes it back out.
    # Settings has a default for each of these, which is what the suite asserts on.
    for env in [k for k in os.environ if k.startswith("WB_")]:
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setenv("WB_TRACE_DB_URL", "sqlite+aiosqlite:///:memory:")
    # Neuter dotenv loading first, then drop any keys already in os.environ — so a
    # later get_settings() (which calls load_dotenv) cannot bring them back.
    monkeypatch.setattr(_config, "load_dotenv", lambda *a, **k: False)
    # Settings declares env_file=".env", and pydantic-settings reads that file
    # itself — neutering load_dotenv above does not stop it. Detach the file too,
    # or every WB_* value in a developer's .env (routing flags, model names, URLs)
    # silently reshapes the suite: green in CI, red on the machine running the stack.
    monkeypatch.setitem(_config.Settings.model_config, "env_file", None)
    for env in _PROVIDER_KEY_ENVS:
        monkeypatch.delenv(env, raising=False)
    get_settings.cache_clear()
    reset_engine()
    yield
    reset_engine()
    get_settings.cache_clear()
