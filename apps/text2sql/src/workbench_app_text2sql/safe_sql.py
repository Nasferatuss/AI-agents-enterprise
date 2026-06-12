"""Read-only SQL guards (ADR-004): parser validation, table allowlist, forced LIMIT.

Defense in depth:
1. sqlglot parses the query — exactly one statement, top-level SELECT (CTEs and
   UNIONs allowed), and no write/DDL/admin node anywhere in the tree (catches
   PostgreSQL data-modifying CTEs like `WITH x AS (DELETE ...) SELECT ...`).
2. Every referenced table must be in the allowlist.
3. LIMIT is injected when missing and capped when above max_rows.
4. SQLite connections are opened in read-only mode (`mode=ro`); for other
   engines the DB user must be read-only (sandbox DB per ADR-004).
"""

import asyncio

import sqlglot
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlglot import exp

MAX_ROWS = 200

_FORBIDDEN_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Merge,
    exp.TruncateTable,
    exp.Grant,
    exp.Command,  # PRAGMA/ATTACH/EXEC and other raw commands parse as Command
    exp.Set,
    exp.Transaction,
)


class SqlGuardError(Exception):
    """Query rejected by the read-only guards; the message goes back to the model."""


def validate_sql(sql: str, allowed_tables: set[str], dialect: str = "sqlite") -> str:
    """Validate and normalize; returns SQL with LIMIT enforced. Raises SqlGuardError."""
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except sqlglot.errors.ParseError as exc:
        raise SqlGuardError(f"SQL does not parse: {exc}") from exc

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise SqlGuardError("exactly one SQL statement is allowed")
    tree = statements[0]

    if not isinstance(tree, exp.Select | exp.Union):
        raise SqlGuardError("only read-only SELECT queries are allowed")
    for node in tree.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise SqlGuardError(f"forbidden operation: {type(node).__name__.upper()}")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    allowed = {t.lower() for t in allowed_tables}
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if name and name not in allowed and name not in cte_names:
            raise SqlGuardError(f"table '{table.name}' is not in the allowlist: {sorted(allowed)}")

    limit_node = tree.args.get("limit")
    if (
        limit_node is None
        or not isinstance(limit_node.expression, exp.Literal)
        or int(limit_node.expression.this) > MAX_ROWS
    ):
        tree = tree.limit(MAX_ROWS)

    return tree.sql(dialect=dialect)


def _run(engine: Engine, sql: str) -> tuple[list[str], list[list]]:
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = [list(r) for r in result.fetchmany(MAX_ROWS)]
    return columns, rows


async def execute_sql(
    engine: Engine, sql: str, allowed_tables: set[str], dialect: str = "sqlite"
) -> tuple[str, list[str], list[list]]:
    """Validate then execute; returns (normalized sql, columns, rows)."""
    safe_sql = validate_sql(sql, allowed_tables, dialect=dialect)
    try:
        columns, rows = await asyncio.to_thread(_run, engine, safe_sql)
    except SQLAlchemyError as exc:
        raise SqlGuardError(f"execution failed: {getattr(exc, 'orig', exc)}") from exc
    return safe_sql, columns, rows
