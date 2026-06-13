import pytest

from workbench_observability import init_db, reset_engine
from workbench_shared.config import get_settings


@pytest.fixture
async def trace_db(monkeypatch):
    """Fresh in-memory trace store per test."""
    monkeypatch.setenv("WB_TRACE_DB_URL", "sqlite+aiosqlite:///:memory:")
    get_settings.cache_clear()
    reset_engine()
    await init_db()
    yield
    reset_engine()
    get_settings.cache_clear()
