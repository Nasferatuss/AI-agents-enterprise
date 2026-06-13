"""Adversarial SQL guard tests (Phase 4 security QA).

These are the payloads a prompt-injected or jailbroken model might emit through
the run_sql tool. The guard (ADR-004) must reject every one before execution.
"""

import pytest

from workbench_app_text2sql.safe_sql import SqlGuardError, validate_sql

ALLOWED = {"customers", "products", "orders", "order_items"}


# Each pair: (payload, dialect). All must be rejected by validate_sql.
INJECTION_PAYLOADS = [
    # --- stacked / multi-statement ---
    ("SELECT 1; DROP TABLE customers", "sqlite"),
    ("SELECT * FROM customers; DELETE FROM customers", "sqlite"),
    ("SELECT * FROM customers WHERE 1=1; UPDATE customers SET name='x'", "sqlite"),
    # --- data-modifying CTE (PostgreSQL) hiding behind a SELECT shell ---
    ("WITH x AS (DELETE FROM customers RETURNING *) SELECT * FROM x", "postgres"),
    ("WITH x AS (UPDATE customers SET name='h' RETURNING id) SELECT * FROM x", "postgres"),
    (
        "WITH x AS (INSERT INTO customers(id,name) VALUES(1,'h') RETURNING id) SELECT * FROM x",
        "postgres",
    ),
    # --- subquery / set-op reaching a non-allowlisted table ---
    ("SELECT * FROM customers WHERE id IN (SELECT id FROM secret_table)", "sqlite"),
    ("SELECT (SELECT password FROM admin_users LIMIT 1) FROM customers", "sqlite"),
    ("SELECT name FROM customers UNION SELECT name FROM pg_catalog.pg_tables", "postgres"),
    ("SELECT * FROM orders JOIN forbidden_table ON 1=1", "sqlite"),
    # --- filesystem / code-loading functions (no table arg → table allowlist blind) ---
    ("SELECT load_extension('/tmp/evil.so')", "sqlite"),
    ("SELECT pg_read_file('/etc/passwd')", "postgres"),
    ("SELECT lo_import('/etc/passwd')", "postgres"),
    ("SELECT name, pg_ls_dir('/') FROM customers", "postgres"),
    # --- admin / raw commands ---
    ("PRAGMA writable_schema = ON", "sqlite"),
    ("ATTACH DATABASE '/tmp/evil.db' AS evil", "sqlite"),
    ("VACUUM", "sqlite"),
    ("DROP TABLE customers", "sqlite"),
    ("CREATE TABLE evil (id INT)", "sqlite"),
    ("ALTER TABLE customers ADD COLUMN evil TEXT", "sqlite"),
    ("GRANT ALL ON customers TO PUBLIC", "postgres"),
    # --- malformed / not a query ---
    ("'; DROP TABLE customers; --", "sqlite"),
    ("not sql at all (((", "sqlite"),
]


@pytest.mark.parametrize("payload,dialect", INJECTION_PAYLOADS)
def test_injection_payload_rejected(payload, dialect):
    with pytest.raises(SqlGuardError):
        validate_sql(payload, ALLOWED, dialect=dialect)


def test_comment_cannot_smuggle_a_second_statement():
    # A line comment after a single SELECT is fine (one statement); a comment
    # cannot hide a second statement — that still parses as two statements.
    ok = validate_sql("SELECT name FROM customers -- harmless comment", ALLOWED)
    assert "customers" in ok.lower()
    with pytest.raises(SqlGuardError):
        validate_sql("SELECT name FROM customers;\n-- x\nDROP TABLE customers", ALLOWED)


def test_legitimate_analytics_query_passes():
    # A real BI query with CTE, joins and aggregation must NOT be rejected.
    sql = validate_sql(
        """WITH revenue AS (
             SELECT order_id, SUM(quantity * unit_price) AS total
             FROM order_items GROUP BY order_id
           )
           SELECT c.name, SUM(r.total) AS lifetime
           FROM revenue r
           JOIN orders o ON o.id = r.order_id
           JOIN customers c ON c.id = o.customer_id
           WHERE o.status = 'completed'
           GROUP BY c.name ORDER BY lifetime DESC""",
        ALLOWED,
    )
    assert "LIMIT" in sql.upper()
