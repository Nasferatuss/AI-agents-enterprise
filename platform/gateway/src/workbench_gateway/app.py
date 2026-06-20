"""FastAPI application factory for the API Gateway."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from workbench_app_autonomous.api import router as autonomous_router

from workbench_app_compliance.api import router as compliance_router
from workbench_app_cua.api import router as cua_router
from workbench_app_incident.api import router as incident_router
from workbench_app_process.api import router as process_router
from workbench_app_research.api import router as research_router
from workbench_app_text2sql.api import router as text2sql_router
from workbench_gateway import __version__
from workbench_gateway.routes import agents, evals, health, llm, observability, rag
from workbench_gateway.security import (
    ApiKeyMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    validate_production_security,
)
from workbench_observability import init_db
from workbench_orchestrator.api import router as workflows_router
from workbench_shared.config import get_settings
from workbench_shared.logging import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()  # create the trace store schema (ADR-006)
        log.info("trace store ready", url=get_settings().trace_db_url.split("@")[-1])
    except Exception as exc:  # noqa: BLE001 — trace store is best-effort, never blocks boot
        log.warning("trace store init failed; tracing disabled", error=str(exc))
    yield


def create_app() -> FastAPI:
    configure_logging()
    # HIGH-2 / MED-1: refuse to boot a production gateway that is missing auth,
    # the approval-token gate, or an explicit CORS allow-list. No-op in dev/test.
    validate_production_security(get_settings())
    app = FastAPI(
        title="Enterprise AI Agent Workbench — API Gateway",
        version=__version__,
        lifespan=lifespan,
    )
    # Middleware runs outermost-first (last added → first executed):
    # security-headers, then rate-limit, then API key, then CORS. The auth/rate
    # middlewares are no-ops unless configured; security headers always apply.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["GET", "POST"],  # the only methods the console uses
        allow_headers=["Content-Type", "X-Approval-Token", "X-API-Key"],
    )
    app.add_middleware(ApiKeyMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)  # outermost → stamps every response
    app.include_router(health.router)
    app.include_router(llm.router)
    app.include_router(agents.router)
    app.include_router(rag.router)
    app.include_router(evals.router)
    app.include_router(observability.router)
    app.include_router(workflows_router)
    app.include_router(text2sql_router)  # demo apps mount here (composition root)
    app.include_router(process_router)
    app.include_router(compliance_router)
    app.include_router(research_router)
    app.include_router(cua_router)
    app.include_router(incident_router)
    app.include_router(autonomous_router)
    log.info("gateway configured", version=__version__)
    return app


app = create_app()
