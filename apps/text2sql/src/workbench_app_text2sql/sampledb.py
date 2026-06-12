"""Deterministic sample retail database (sandbox DB per ADR-004).

Small but realistic BI schema: customers → orders → order_items → products.
Created on first use when the configured sqlite file is missing.
"""

import random
import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT NOT NULL,
    segment TEXT NOT NULL CHECK (segment IN ('enterprise', 'smb', 'consumer')),
    signed_up DATE NOT NULL
);
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit_price REAL NOT NULL
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    ordered_at DATE NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('completed', 'cancelled', 'pending'))
);
CREATE TABLE order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL
);
"""

_CUSTOMERS = [
    ("Acme Corp", "DE", "enterprise"),
    ("Globex", "US", "enterprise"),
    ("Initech", "US", "smb"),
    ("Umbrella Ltd", "UK", "smb"),
    ("Wayne Enterprises", "US", "enterprise"),
    ("Stark Industries", "US", "enterprise"),
    ("Pied Piper", "US", "smb"),
    ("Hooli", "US", "enterprise"),
    ("Wonka GmbH", "DE", "consumer"),
    ("Tyrell Corp", "JP", "enterprise"),
]

_PRODUCTS = [
    ("Workbench License", "software", 1200.0),
    ("Support Plan Gold", "services", 800.0),
    ("Support Plan Silver", "services", 400.0),
    ("GPU Node Hour", "infrastructure", 2.5),
    ("Vector DB Cluster", "infrastructure", 350.0),
    ("Training Workshop", "services", 1500.0),
    ("Eval Pack", "software", 250.0),
    ("Trace Storage TB", "infrastructure", 90.0),
]


def create_sample_db(path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)

    conn = sqlite3.connect(path)
    try:
        conn.executescript(_SCHEMA)
        for i, (name, country, segment) in enumerate(_CUSTOMERS, start=1):
            signup = f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
            conn.execute(
                "INSERT INTO customers VALUES (?, ?, ?, ?, ?)", (i, name, country, segment, signup)
            )
        for i, (name, category, price) in enumerate(_PRODUCTS, start=1):
            conn.execute("INSERT INTO products VALUES (?, ?, ?, ?)", (i, name, category, price))

        item_id = 1
        for order_id in range(1, 41):
            customer_id = rng.randint(1, len(_CUSTOMERS))
            ordered_at = f"2026-{rng.randint(1, 5):02d}-{rng.randint(1, 28):02d}"
            status = rng.choices(["completed", "cancelled", "pending"], weights=[8, 1, 1])[0]
            conn.execute(
                "INSERT INTO orders VALUES (?, ?, ?, ?)",
                (order_id, customer_id, ordered_at, status),
            )
            for _ in range(rng.randint(1, 4)):
                product_id = rng.randint(1, len(_PRODUCTS))
                quantity = rng.randint(1, 10)
                unit_price = _PRODUCTS[product_id - 1][2]
                conn.execute(
                    "INSERT INTO order_items VALUES (?, ?, ?, ?, ?)",
                    (item_id, order_id, product_id, quantity, unit_price),
                )
                item_id += 1
        conn.commit()
    finally:
        conn.close()
    return path
