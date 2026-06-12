"""FastAPI application factory for the API Gateway."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from workbench_app_text2sql.api import router as text2sql_router
from workbench_gateway import __version__
from workbench_gateway.routes import agents, evals, health, llm, rag
from workbench_shared.config import get_settings
from workbench_shared.logging import configure_logging, get_logger

log = get_logger(__name__)


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="Enterprise AI Agent Workbench — API Gateway",
        version=__version__,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(llm.router)
    app.include_router(agents.router)
    app.include_router(rag.router)
    app.include_router(evals.router)
    app.include_router(text2sql_router)  # demo apps mount here (composition root)
    log.info("gateway configured", version=__version__)
    return app


app = create_app()
