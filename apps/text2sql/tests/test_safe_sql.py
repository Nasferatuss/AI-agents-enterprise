import pytest
from sqlalchemy import create_engine

from workbench_capabilities import (
    MAX_ROWS,
    SqlGuardError,
    create_sample_db,
    execute_sql,
    validate_sql,
)

ALLOWED = {"customers", "products", "orders", "order_items"}


# --- validation: what must pass ---


def test_plain_select_gets_limit():
    sql = validate_sql("SELECT name FROM customers", ALLOWED)
    assert f"LIMIT {MAX_ROWS}" in sql


def test_existing_small_limit_is_kept():
    sql = validate_sql("SELECT name FROM customers LIMIT 5", ALLOWED)
    assert "LIMIT 5" in sql


def test_oversized_limit_is_capped():
    sql = validate_sql("SELECT name FROM customers LIMIT 100000", ALLOWED)
    assert f"LIMIT {MAX_ROWS}" in sql
    assert "100000" not in sql


def test_small_offset_is_kept():
    sql = validate_sql("SELECT name FROM customers LIMIT 5 OFFSET 100", ALLOWED)
    assert "OFFSET 100" in sql


def test_scan_amplifying_offset_is_rejected():
    # LIMIT is capped but a huge OFFSET still forces the engine to skip ~100M rows.
    with pytest.raises(SqlGuardError, match="OFFSET too large"):
        validate_sql("SELECT name FROM customers LIMIT 200 OFFSET 99999999", ALLOWED)


def test_cte_and_join_allowed():
    sql = validate_sql(
        """WITH totals AS (
             SELECT order_id, SUM(quantity * unit_price) AS total FROM order_items GROUP BY order_id
           )
           SELECT c.name, SUM(t.total) FROM totals t
           JOIN orders o ON o.id = t.order_id
           JOIN customers c ON c.id = o.customer_id
           GROUP BY c.name ORDER BY 2 DESC""",
        ALLOWED,
    )
    assert sql.upper().startswith("WITH")


def test_union_allowed():
    sql = validate_sql("SELECT name FROM customers UNION SELECT name FROM products", ALLOWED)
    assert "UNION" in sql.upper()


# --- validation: what must be rejected ---


@pytest.mark.parametrize(
    "bad",
    [
        "INSERT INTO customers (name) VALUES ('x')",
        "UPDATE customers SET name = 'x'",
        "DELETE FROM customers",
        "DROP TABLE customers",
        "CREATE TABLE evil (id INT)",
        "ALTER TABLE customers ADD COLUMN evil TEXT",
        "SELECT 1; DELETE FROM customers",  # multiple statements
        "PRAGMA writable_schema = ON",
        "ATTACH DATABASE '/tmp/evil.db' AS evil",
        "WITH x AS (DELETE FROM customers RETURNING *) SELECT * FROM x",  # DML CTE
        "SELECT * FROM secret_table",  # not in allowlist
        "this is not sql at all (",
    ],
)
def test_rejected(bad):
    with pytest.raises(SqlGuardError):
        validate_sql(bad, ALLOWED, dialect="postgres" if "RETURNING" in bad else "sqlite")


def test_cte_name_does_not_need_allowlist():
    sql = validate_sql("WITH t AS (SELECT id FROM orders) SELECT * FROM t", ALLOWED)
    assert "WITH" in sql.upper()


# --- execution against the read-only sample DB ---


@pytest.fixture
def engine(tmp_path):
    db = create_sample_db(tmp_path / "retail.db")
    return create_engine(f"sqlite:///file:{db}?mode=ro&uri=true")


async def test_execute_returns_rows(engine):
    sql, columns, rows = await execute_sql(
        engine, "SELECT id, name FROM customers ORDER BY id", ALLOWED
    )
    assert columns == ["id", "name"]
    assert rows[0] == [1, "Acme Corp"]
    assert len(rows) == 10


async def test_readonly_connection_blocks_writes_even_past_validation(engine):
    from workbench_capabilities.sql_guard import _run

    with pytest.raises(Exception, match="readonly|attempt to write"):
        _run(
            engine,
            "INSERT INTO customers (id, name, country, segment, signed_up) "
            "VALUES (99, 'X', 'US', 'smb', '2026-01-01')",
        )


async def test_execution_error_is_guard_error(engine):
    with pytest.raises(SqlGuardError, match="execution failed"):
        await execute_sql(engine, "SELECT no_such_column FROM customers", ALLOWED)
