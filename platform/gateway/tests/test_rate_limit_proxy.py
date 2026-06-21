"""Rate-limiter client identity: socket peer by default, X-Forwarded-For when trusted."""

from collections import deque
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


def test_reap_idle_drops_silent_ips_keeps_active():
    mw = RateLimitMiddleware(app=None)
    now = 1000.0
    mw._hits["idle"] = deque([now - 120])  # last hit > window ago → reapable
    mw._hits["active"] = deque([now - 5])  # within window → kept
    mw._hits["empty"] = deque()  # never any hits → reapable
    mw._reap_idle(now)  # last_cleanup=0 so the interval gate is open
    assert set(mw._hits) == {"active"}  # idle + empty buckets freed, no unbounded leak
