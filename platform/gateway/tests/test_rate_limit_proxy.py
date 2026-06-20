"""Rate-limiter client identity: socket peer by default, X-Forwarded-For when trusted."""

from types import SimpleNamespace

from workbench_gateway.security import RateLimitMiddleware
from workbench_shared.config import get_settings


def _req(xff: str | None, host: str):
    headers = {"x-forwarded-for": xff} if xff is not None else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


def test_client_ip_uses_socket_peer_by_default(monkeypatch):
    monkeypatch.setenv("WB_TRUST_PROXY_HEADERS", "false")
    get_settings.cache_clear()
    try:
        ip = RateLimitMiddleware._client_ip(_req("1.2.3.4", "10.0.0.1"))
        assert ip == "10.0.0.1"  # spoofable header ignored
    finally:
        get_settings.cache_clear()


def test_client_ip_trusts_forwarded_when_enabled(monkeypatch):
    monkeypatch.setenv("WB_TRUST_PROXY_HEADERS", "true")
    get_settings.cache_clear()
    try:
        ip = RateLimitMiddleware._client_ip(_req("1.2.3.4, 5.6.7.8", "10.0.0.1"))
        assert ip == "1.2.3.4"  # first hop = real client
    finally:
        get_settings.cache_clear()
