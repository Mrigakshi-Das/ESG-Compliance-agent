"""Phase 2 data tests: confirm the synthetic dataset loads from both CSV and
SQLite, that the two agree, and that the structural/known-issue checks in
`app.data.validate_data` pass. Not agent tests -- those come in Phase 10.
"""

import csv

import pytest

from app.data.constants import SEED_CSV_DIR
from app.data.db import TABLES, fetch_all
from app.data.validate_data import known_issue_checks, structural_checks


def _read_csv(table: str) -> list[dict]:
    with (SEED_CSV_DIR / f"{table}.csv").open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.mark.parametrize("table", TABLES)
def test_csv_loads_and_is_nonempty(table):
    rows = _read_csv(table)
    assert len(rows) > 0


@pytest.mark.parametrize("table", TABLES)
def test_sqlite_matches_csv(table):
    csv_rows = _read_csv(table)
    db_rows = fetch_all(table)
    assert len(csv_rows) == len(db_rows)
    assert csv_rows == db_rows


def test_structural_checks_pass():
    errors = structural_checks()
    assert errors == []


def test_known_issues_all_confirmed():
    findings = known_issue_checks()
    unexpected = [f for f in findings if not f.startswith("OK")]
    assert unexpected == [], f"Known-issue checks did not match expectations: {unexpected}"
