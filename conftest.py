"""Repo-wide test isolation for the observability trace store.

Every test points the trace store at a throwaway in-memory sqlite DB so that
best-effort recording in the run routes never touches a real DB or leaves a
data/traces.db file behind. Tests that assert on recorded traces call init_db()
themselves (see platform/observability/tests/conftest.py and the gateway
observability test).
"""

import pytest

from workbench_observability import reset_engine
from workbench_shared.config import get_settings


@pytest.fixture(autouse=True)
def _isolate_trace_store(monkeypatch):
    monkeypatch.setenv("WB_TRACE_DB_URL", "sqlite+aiosqlite:///:memory:")
    get_settings.cache_clear()
    reset_engine()
    yield
    reset_engine()
    get_settings.cache_clear()
