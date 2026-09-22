"""Validates the synthetic dataset itself: that every CSV/SQLite table has
the shape it's supposed to have, and that the deliberate data-quality
issues catalogued in KNOWN_DATA_ISSUES.md are present exactly where
expected -- no more, no less.

This is a Phase 2 data-QA tool, distinct from the agent's own runtime Data
Validator (Phase 5/6 `app/tools`), which will validate data *as the agent
retrieves it* during a live run. This script instead validates the seed
data at rest, so later phases can build on it trusting it is what
KNOWN_DATA_ISSUES.md says it is.

Run with: python -m app.data.validate_data
"""

from __future__ import annotations

from collections import Counter
from datetime import date

from app.data.constants import PERIODS, PLANTS
from app.data.db import fetch_all

TODAY = date(2026, 9, 12)


def _as_float(value: str) -> float:
    return float(value)


def _as_date(value: str) -> date:
    return date.fromisoformat(value)


# ---------------------------------------------------------------------------
# Structural checks -- these must always pass; a failure means the generator
# or the loader is broken, not that a known issue was found.
# ---------------------------------------------------------------------------


def check_plant_ids(table: str, rows: list[dict]) -> list[str]:
    bad = sorted({r["plant_id"] for r in rows if r["plant_id"] not in PLANTS})
    return [f"{table}: unknown plant_id(s) {bad}"] if bad else []


def check_periods(table: str, rows: list[dict]) -> list[str]:
    bad = sorted({r["period"] for r in rows if r["period"] not in PERIODS})
    return [f"{table}: unknown period(s) {bad}"] if bad else []


def check_numeric_fields(table: str, rows: list[dict], fields: list[str]) -> list[str]:
    errors = []
    for row in rows:
        for field in fields:
            try:
                _as_float(row[field])
            except (TypeError, ValueError):
                errors.append(
                    f"{table}: non-numeric {field}={row[field]!r} "
                    f"(plant={row.get('plant_id')}, period={row.get('period')})"
                )
    return errors


def check_dates(table: str, rows: list[dict], fields: list[str]) -> list[str]:
    errors = []
    for row in rows:
        for field in fields:
            value = row.get(field)
            if not value:
                continue  # blank is valid for e.g. evidence.expiry_date
            try:
                _as_date(value)
            except ValueError:
                errors.append(f"{table}: unparseable date {field}={value!r} in row {row}")
    return errors


def structural_checks() -> list[str]:
    errors: list[str] = []

    production = fetch_all("production")
    energy = fetch_all("energy")
    emissions = fetch_all("emissions")
    water = fetch_all("water")
    waste = fetch_all("waste")
    fuel_quality = fetch_all("fuel_quality")
    weather = fetch_all("weather")
    maintenance = fetch_all("maintenance")
    evidence = fetch_all("evidence")

    for table, rows in [
        ("production", production),
        ("energy", energy),
        ("emissions", emissions),
        ("water", water),
        ("waste", waste),
        ("fuel_quality", fuel_quality),
        ("weather", weather),
    ]:
        errors += check_plant_ids(table, rows)
        errors += check_periods(table, rows)
    errors += check_plant_ids("maintenance", maintenance)
    errors += check_plant_ids("evidence", evidence)

    errors += check_numeric_fields(
        "production", production, ["clinker_production_tonnes", "cement_production_tonnes", "operating_days"]
    )
    errors += check_numeric_fields(
        "energy", energy,
        ["electricity_consumption_mwh", "thermal_energy_gj", "fuel_consumption_tonnes", "renewable_energy_mwh"],
    )
    errors += check_numeric_fields("emissions", emissions, ["scope_1_tco2e", "scope_2_tco2e", "total_tco2e"])
    errors += check_numeric_fields(
        "water", water, ["water_withdrawal_m3", "water_consumption_m3", "recycled_water_m3"]
    )
    errors += check_numeric_fields(
        "waste", waste, ["waste_generated_tonnes", "waste_recycled_tonnes", "waste_utilized_tonnes"]
    )
    errors += check_numeric_fields(
        "fuel_quality", fuel_quality,
        ["gross_calorific_value_kcal_per_kg", "ash_content_pct", "moisture_content_pct", "sulphur_content_pct"],
    )
    errors += check_numeric_fields(
        "weather", weather, ["avg_ambient_temp_c", "rainfall_mm", "avg_humidity_pct"]
    )

    # emissions arithmetic must foot: scope1 + scope2 == total, for every row
    for row in emissions:
        s1, s2, total = _as_float(row["scope_1_tco2e"]), _as_float(row["scope_2_tco2e"]), _as_float(row["total_tco2e"])
        if abs((s1 + s2) - total) > 0.5:
            errors.append(f"emissions: scope1+scope2 != total for {row['plant_id']} {row['period']}")

    errors += check_dates("maintenance", maintenance, ["maintenance_date", "planned_next_maintenance"])
    errors += check_dates("evidence", evidence, ["document_date", "expiry_date"])

    # energy/emissions/water/waste must cover the full 3-plant x 6-period
    # grid with no gaps -- only production is allowed a deliberate gap.
    full_grid = {(p, per) for p in PLANTS for per in PERIODS}
    for table, rows in [
        ("energy", energy), ("emissions", emissions), ("water", water), ("waste", waste),
        ("fuel_quality", fuel_quality), ("weather", weather),
    ]:
        present = {(r["plant_id"], r["period"]) for r in rows}
        missing = full_grid - present
        if missing:
            errors.append(f"{table}: unexpectedly missing {sorted(missing)} (only production.csv should have gaps)")

    return errors


# ---------------------------------------------------------------------------
# Known-issue checks -- confirm each deliberate issue from
# KNOWN_DATA_ISSUES.md is present exactly where documented.
# ---------------------------------------------------------------------------


def known_issue_checks() -> list[str]:
    findings: list[str] = []
    production = fetch_all("production")
    waste = fetch_all("waste")
    evidence = fetch_all("evidence")

    # Issue #1: Plant C / FY2025-26 Q3 production missing
    combos = Counter((r["plant_id"], r["period"]) for r in production)
    if combos.get(("Plant C", "FY2025-26 Q3"), 0) != 0:
        findings.append("EXPECTED ISSUE #1 NOT FOUND: Plant C FY2025-26 Q3 production row exists")
    else:
        findings.append("OK issue #1: Plant C FY2025-26 Q3 production is missing, as documented")

    # Issue #2: Plant C / FY2025-26 Q2 production duplicated with conflicting values
    q2_rows = [r for r in production if (r["plant_id"], r["period"]) == ("Plant C", "FY2025-26 Q2")]
    if len(q2_rows) != 2:
        findings.append(f"EXPECTED ISSUE #2 MISMATCH: found {len(q2_rows)} Plant C FY2025-26 Q2 production rows, expected 2")
    elif q2_rows[0]["clinker_production_tonnes"] == q2_rows[1]["clinker_production_tonnes"]:
        findings.append("EXPECTED ISSUE #2 NOT FOUND: the two Plant C FY2025-26 Q2 rows agree")
    else:
        findings.append("OK issue #2: Plant C FY2025-26 Q2 has two conflicting production rows")

    # Overall: exactly one plant/period combo should be duplicated, and
    # exactly one should be missing, with no other combo affected.
    all_combos = {(p, per) for p in PLANTS for per in PERIODS}
    missing_combos = all_combos - set(combos)
    duplicated_combos = {k for k, v in combos.items() if v > 1}
    if missing_combos != {("Plant C", "FY2025-26 Q3")}:
        findings.append(f"UNEXPECTED missing production combos: {sorted(missing_combos)}")
    if duplicated_combos != {("Plant C", "FY2025-26 Q2")}:
        findings.append(f"UNEXPECTED duplicated production combos: {sorted(duplicated_combos)}")

    # Issue #3: duplicate document_id in evidence.csv
    doc_id_counts = Counter(r["document_id"] for r in evidence)
    dupes = {k for k, v in doc_id_counts.items() if v > 1}
    if dupes != {"DOC-C-2026-014"}:
        findings.append(f"EXPECTED ISSUE #3 MISMATCH: duplicate document_id(s) found = {sorted(dupes)}")
    else:
        findings.append("OK issue #3: DOC-C-2026-014 is duplicated in evidence.csv, as documented")

    # Issue #4: expired evidence present
    expired = [r for r in evidence if r["status"] == "Expired"]
    if not expired:
        findings.append("EXPECTED ISSUE #4 NOT FOUND: no evidence row has status=Expired")
    else:
        for r in expired:
            if r["expiry_date"] and _as_date(r["expiry_date"]) >= TODAY:
                findings.append(f"INCONSISTENT: {r['document_id']} marked Expired but expiry_date is not in the past")
        findings.append(f"OK issue #4: {len(expired)} expired evidence row(s) found ({[r['document_id'] for r in expired]})")

    # Issue #7: impossible waste value (recycled > generated)
    impossible = [
        r for r in waste
        if _as_float(r["waste_recycled_tonnes"]) > _as_float(r["waste_generated_tonnes"])
    ]
    expected_key = ("Plant B", "FY2025-26 Q3")
    found_keys = {(r["plant_id"], r["period"]) for r in impossible}
    if found_keys != {expected_key}:
        findings.append(f"EXPECTED ISSUE #7 MISMATCH: impossible waste rows at {sorted(found_keys)}, expected {[expected_key]}")
    else:
        findings.append("OK issue #7: exactly one impossible waste_recycled > waste_generated row, at Plant B FY2025-26 Q3")

    return findings


def main() -> int:
    print("=== Structural checks ===")
    structural_errors = structural_checks()
    if structural_errors:
        for e in structural_errors:
            print(f"FAIL: {e}")
    else:
        print("All structural checks passed.")

    print("\n=== Known data-issue checks ===")
    for line in known_issue_checks():
        print(line)

    return 1 if structural_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
