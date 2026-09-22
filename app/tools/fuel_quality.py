"""Tool: get_fuel_quality_data.

Agent-callable wrapper around `app.data.fuel_quality.FuelQualityDataSource`.
Same validate/resolve/report shape as every other domain tool -- see
`app/tools/production.py` for the pattern this follows.
"""

from typing import Any

from app.data.fuel_quality import FuelQualityDataSource
from app.tools._common import resolve_rows, source_systems, validate_period, validate_plant
from app.tools.schema import ToolParam, ToolSpec

_source = FuelQualityDataSource()

GET_FUEL_QUALITY_DATA_SPEC = ToolSpec(
    name="get_fuel_quality_data",
    description=(
        "Retrieve kiln fuel quality (calorific value, ash/moisture/sulphur "
        "content) for one plant and reporting period."
    ),
    inputs=[
        ToolParam("plant", "str", True, "One of the configured plant identifiers, e.g. 'Plant A'."),
        ToolParam("period", "str", True, "A configured fiscal-quarter period, e.g. 'FY2025-26 Q2'."),
    ],
    output_description=(
        "{status: 'ok'|'missing'|'conflict', plant, period, values: dict|None, "
        "issues: list[str], source_system, raw_records: list[dict]}. Same shape "
        "as get_production_data."
    ),
    raises="ToolInputError if plant or period is not one of the configured values.",
)


def get_fuel_quality_data(plant: str, period: str) -> dict[str, Any]:
    validate_plant(plant)
    validate_period(period)

    rows = _source.fetch(plant, period)
    status = resolve_rows(rows)
    issues: list[str] = []
    values: dict[str, Any] | None = None

    if status == "empty":
        issues.append(f"No fuel quality record found for {plant} / {period}.")
        result_status = "missing"
    elif status in ("ok", "duplicate"):
        r = rows[0]
        values = {
            "gross_calorific_value_kcal_per_kg": r["gross_calorific_value_kcal_per_kg"],
            "ash_content_pct": r["ash_content_pct"],
            "moisture_content_pct": r["moisture_content_pct"],
            "sulphur_content_pct": r["sulphur_content_pct"],
        }
        if status == "duplicate":
            issues.append(f"{len(rows)} identical fuel quality records found for {plant} / {period} (logged more than once).")
        result_status = "ok"
    else:  # conflict
        systems = source_systems(rows)
        issues.append(
            f"{len(rows)} conflicting fuel quality records found for {plant} / {period} "
            f"across source system(s) {systems}: values disagree and were not merged."
        )
        result_status = "conflict"

    return {
        "status": result_status,
        "plant": plant,
        "period": period,
        "values": values,
        "issues": issues,
        "source_system": source_systems(rows) if rows else None,
        "raw_records": rows,
    }
