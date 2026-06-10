"""FastAPI application factory for the API Gateway."""

from fastapi import FastAPI

from workbench_gateway import __version__
from workbench_gateway.routes import health
from workbench_shared.logging import configure_logging, get_logger

log = get_logger(__name__)


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="Enterprise AI Agent Workbench — API Gateway",
        version=__version__,
    )
    app.include_router(health.router)
    log.info("gateway configured", version=__version__)
    return app


app = create_app()
