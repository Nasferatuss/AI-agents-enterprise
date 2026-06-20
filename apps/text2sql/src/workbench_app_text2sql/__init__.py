"""Text-to-SQL BI agent (MVP module #2): question → SQL → result → explanation."""

from workbench_capabilities import (
    SqlGuardError,
    execute_sql,
    get_engine,
    validate_sql,
)

from workbench_app_text2sql.agent import build_agent
from workbench_app_text2sql.api import router

__all__ = [
    "SqlGuardError",
    "build_agent",
    "execute_sql",
    "get_engine",
    "router",
    "validate_sql",
]
