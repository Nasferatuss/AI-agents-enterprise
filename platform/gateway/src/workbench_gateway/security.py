"""Optional gateway auth + rate limiting (Phase 5 hardening).

Both default to OFF so the local demo and the test suite stay open. They turn on
purely from config, with no code change:
- WB_API_KEY → every /v1/* request must carry a matching X-API-Key header.
- WB_RATE_LIMIT_PER_MIN → cap POST /v1/* per client IP per minute.

The rate limiter is a per-process fixed window — fine for a single instance /
demo; a multi-instance deployment would move the counter to Redis.
"""

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from workbench_shared.config import get_settings
from workbench_shared.logging import get_logger

log = get_logger(__name__)

_PROTECTED = "/v1"


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        key = get_settings().api_key
        if (
            key
            and request.url.path.startswith(_PROTECTED)
            and request.headers.get("x-api-key") != key
        ):
            return JSONResponse({"detail": "invalid or missing API key"}, status_code=401)
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        limit = get_settings().rate_limit_per_min
        if limit and request.method == "POST" and request.url.path.startswith(_PROTECTED):
            client = request.client.host if request.client else "anon"
            now = time.monotonic()
            window = self._hits[client]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= limit:
                log.warning("rate limit exceeded", client=client, path=request.url.path)
                return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)
            window.append(now)
        return await call_next(request)
