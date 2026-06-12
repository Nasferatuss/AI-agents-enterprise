"""Text-to-SQL BI agent (MVP module #2): question → SQL → result → explanation."""

from workbench_app_text2sql.agent import build_agent, get_engine
from workbench_app_text2sql.api import router
from workbench_app_text2sql.safe_sql import SqlGuardError, execute_sql, validate_sql

__all__ = [
    "SqlGuardError",
    "build_agent",
    "execute_sql",
    "get_engine",
    "router",
    "validate_sql",
]
