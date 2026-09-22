"""Tool: get_production_data.

Agent-callable wrapper around `app.data.production.ProductionDataSource`.
Validates plant/period, resolves how many raw rows matched, and returns a
structured result the agent can act on without ever seeing raw rows itself.
"""

from typing import Any

from app.data.production import ProductionDataSource
from app.tools._common import resolve_rows, source_systems, validate_period, validate_plant
from app.tools.schema import ToolParam, ToolSpec

_source = ProductionDataSource()

GET_PRODUCTION_DATA_SPEC = ToolSpec(
    name="get_production_data",
    description=(
        "Retrieve clinker/cement production and operating days for one plant "
        "and reporting period."
    ),
    inputs=[
        ToolParam("plant", "str", True, "One of the configured plant identifiers, e.g. 'Plant A'."),
        ToolParam("period", "str", True, "A configured fiscal-quarter period, e.g. 'FY2025-26 Q2'."),
    ],
    output_description=(
        "{status: 'ok'|'missing'|'conflict', plant, period, values: dict|None, "
        "issues: list[str], source_system, raw_records: list[dict]}. `values` is "
        "populated only when status == 'ok'; on 'conflict' every disagreeing "
        "record is in raw_records and values is None so nothing is silently picked."
    ),
    raises="ToolInputError if plant or period is not one of the configured values.",
)


def get_production_data(plant: str, period: str) -> dict[str, Any]:
    validate_plant(plant)
    validate_period(period)

    rows = _source.fetch(plant, period)
    status = resolve_rows(rows)
    issues: list[str] = []
    values: dict[str, Any] | None = None

    if status == "empty":
        issues.append(f"No production record found for {plant} / {period}.")
        result_status = "missing"
    elif status in ("ok", "duplicate"):
        r = rows[0]
        values = {
            "clinker_production_tonnes": r["clinker_production_tonnes"],
            "cement_production_tonnes": r["cement_production_tonnes"],
            "operating_days": r["operating_days"],
        }
        if status == "duplicate":
            issues.append(f"{len(rows)} identical production records found for {plant} / {period} (logged more than once).")
        result_status = "ok"
    else:  # conflict
        systems = source_systems(rows)
        issues.append(
            f"{len(rows)} conflicting production records found for {plant} / {period} "
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
