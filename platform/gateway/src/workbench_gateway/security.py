"""Optional gateway auth + rate limiting (Phase 5 hardening).

Both default to OFF so the local demo and the test suite stay open. They turn on
purely from config, with no code change:
- WB_API_KEY → every /v1/* request must carry a matching X-API-Key header.
- WB_RATE_LIMIT_PER_MIN → cap POST /v1/* per client IP per minute.

The rate limiter is a per-process fixed window — fine for a single instance /
demo; a multi-instance deployment would move the counter to Redis.
"""

import hmac
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from workbench_shared.config import Settings, get_settings
from workbench_shared.logging import get_logger

log = get_logger(__name__)

_PROTECTED = "/v1"

# Static headers stamped on every response (LOW-2). Cheap defence-in-depth for an
# API: stop MIME sniffing, deny framing, and never leak the referrer. No CSP —
# it brings no value to a JSON API and risks breaking the Swagger UI assets.
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # Browsers honour HSTS only over HTTPS (ignored on plain-http localhost), so it is
    # safe to stamp always; in a real TLS deployment it blocks the first-connection
    # downgrade. 2 years + subdomains is the conventional strong value.
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}


class ProductionConfigError(RuntimeError):
    """Raised at startup when env=prod is missing required security config."""


def validate_production_security(settings: Settings) -> None:
    """Fail-fast guard for production deployments (HIGH-2 / MED-1).

    In ``dev``/``test`` this is a no-op so the local demo stays open. In ``prod``
    an unauthenticated or wide-open gateway is a deployment mistake, not a valid
    configuration, so we refuse to boot and say exactly which WB_ vars to set.
    """
    if settings.env != "prod":
        return
    missing: list[str] = []
    if not settings.api_key:
        missing.append("WB_API_KEY (gateway /v1/* auth)")
    if not settings.approval_token:
        missing.append("WB_APPROVAL_TOKEN (workflow approve/reject gate)")
    if not settings.cors_origins or "*" in settings.cors_origins:
        missing.append("WB_CORS_ORIGINS (explicit origin list, no '*')")
    if missing:
        raise ProductionConfigError(
            "env=prod requires hardened security config; set: " + "; ".join(missing)
        )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for name, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        key = get_settings().api_key
        # constant-time compare so a timing side-channel can't reveal the key byte by byte.
        if (
            key
            and request.url.path.startswith(_PROTECTED)
            and not hmac.compare_digest(request.headers.get("x-api-key") or "", key)
        ):
            return JSONResponse({"detail": "invalid or missing API key"}, status_code=401)
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    @staticmethod
    def _client_ip(request: Request) -> str:
        # Behind a trusted proxy the socket peer is the proxy, so bucket by the real
        # client from X-Forwarded-For instead — but ONLY when explicitly trusted,
        # since the header is client-controlled and would otherwise be spoofable.
        if get_settings().trust_proxy_headers:
            fwd = request.headers.get("x-forwarded-for")
            if fwd:
                return fwd.split(",")[0].strip()
        return request.client.host if request.client else "anon"

    async def dispatch(self, request: Request, call_next):
        limit = get_settings().rate_limit_per_min
        if limit and request.method == "POST" and request.url.path.startswith(_PROTECTED):
            client = self._client_ip(request)
            now = time.monotonic()
            window = self._hits[client]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= limit:
                log.warning("rate limit exceeded", client=client, path=request.url.path)
                return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)
            window.append(now)
        return await call_next(request)
