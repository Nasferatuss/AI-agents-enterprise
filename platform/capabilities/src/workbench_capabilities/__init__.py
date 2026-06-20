"""Shared platform capabilities reused across apps.

These were extracted out of individual demo apps so that apps depend on the
platform, not on each other (Service-Oriented Core, ADR-001): the read-only SQL
guard + schema reflection, the sample BI database engine, and the governed live
web connectors. The autonomous flagship, the text-to-SQL app, and the deep-
research app all build on these instead of importing one another.
"""

from workbench_capabilities.bi_database import create_sample_db, get_engine
from workbench_capabilities.sql_guard import (
    MAX_ROWS,
    SqlGuardError,
    execute_sql,
    validate_sql,
)
from workbench_capabilities.sql_schema import reflect_tables, schema_description

__all__ = [
    "MAX_ROWS",
    "SqlGuardError",
    "create_sample_db",
    "execute_sql",
    "get_engine",
    "reflect_tables",
    "schema_description",
    "validate_sql",
]
