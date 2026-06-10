"""Liveness and dependency-health endpoints.

Dependency checks are plain TCP reachability probes: in Sprint 0 the gateway
has no DB drivers yet, and a fast socket probe is enough to tell whether the
Compose stack is up without adding dependencies that Sprint 1+ will replace.
"""

import asyncio
from urllib.parse import urlparse

from fastapi import APIRouter

from workbench_gateway import __version__
from workbench_shared.config import get_settings
from workbench_shared.schemas import DependencyStatus, HealthReport

router = APIRouter(tags=["health"])

_PROBE_TIMEOUT_S = 1.0


async def _probe_tcp(name: str, host: str, port: int) -> DependencyStatus:
    try:
        async with asyncio.timeout(_PROBE_TIMEOUT_S):
            _, writer = await asyncio.open_connection(host, port)
        writer.close()
        await writer.wait_closed()
        return DependencyStatus(name=name, state="ok")
    except (OSError, TimeoutError) as exc:
        return DependencyStatus(name=name, state="unreachable", detail=str(exc) or repr(exc))


def _endpoints() -> list[tuple[str, str, int]]:
    s = get_settings()
    pg = urlparse(s.postgres_dsn)
    redis = urlparse(s.redis_url)
    qdrant = urlparse(s.qdrant_url)
    return [
        ("postgres", pg.hostname or "localhost", pg.port or 5432),
        ("redis", redis.hostname or "localhost", redis.port or 6379),
        ("qdrant", qdrant.hostname or "localhost", qdrant.port or 6333),
    ]


@router.get("/healthz", response_model=HealthReport)
async def healthz() -> HealthReport:
    """Liveness: the gateway process itself is up."""
    return HealthReport(service="gateway", version=__version__, env=get_settings().env, status="ok")


@router.get("/healthz/deps", response_model=HealthReport)
async def healthz_deps() -> HealthReport:
    """Readiness: probe platform dependencies (postgres, redis, qdrant)."""
    deps = await asyncio.gather(
        *(_probe_tcp(name, host, port) for name, host, port in _endpoints())
    )
    status = "ok" if all(d.state == "ok" for d in deps) else "degraded"
    return HealthReport(
        service="gateway",
        version=__version__,
        env=get_settings().env,
        status=status,
        dependencies=list(deps),
    )
