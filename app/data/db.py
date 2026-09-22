"""Thin SQLite access helper shared by the validation tests (Phase 2) and,
later, the concrete `PlantDataSource`/`DocumentSource` implementations
(Phase 5). Not a query-building layer -- just a connection + row-dict
convenience so callers aren't hand-parsing CSVs.
"""

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from app.data.constants import DB_PATH

TABLES = (
    "production",
    "energy",
    "emissions",
    "water",
    "waste",
    "fuel_quality",
    "weather",
    "maintenance",
    "evidence",
    "regulatory_targets",
)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"{DB_PATH} does not exist. Run: python -m app.data.generate_synthetic_data"
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def fetch_all(table: str) -> list[dict]:
    if table not in TABLES:
        raise ValueError(f"Unknown table {table!r}; expected one of {TABLES}")
    with connect() as conn:
        rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
        return [dict(row) for row in rows]
