"""Tool: get_waste_data.

Agent-callable wrapper around `app.data.waste.WasteDataSource`. This is
where Plant B's deliberately impossible FY2025-26 Q3 value (recycled >
generated -- see KNOWN_DATA_ISSUES.md #7) is surfaced as an issue.
"""

from typing import Any

from app.data.waste import WasteDataSource
from app.tools._common import resolve_rows, source_systems, validate_period, validate_plant
from app.tools.schema import ToolParam, ToolSpec

_source = WasteDataSource()

GET_WASTE_DATA_SPEC = ToolSpec(
    name="get_waste_data",
    description="Retrieve waste generated, recycled, and utilized for one plant and reporting period.",
    inputs=[
        ToolParam("plant", "str", True, "One of the configured plant identifiers."),
        ToolParam("period", "str", True, "A configured fiscal-quarter period."),
    ],
    output_description=(
        "{status: 'ok'|'missing'|'conflict', plant, period, values: dict|None, "
        "issues: list[str], source_system, raw_records}. `issues` flags an "
        "impossible value if recycled or utilized waste exceeds waste generated."
    ),
    raises="ToolInputError if plant or period is not one of the configured values.",
)


def get_waste_data(plant: str, period: str) -> dict[str, Any]:
    validate_plant(plant)
    validate_period(period)

    rows = _source.fetch(plant, period)
    status = resolve_rows(rows)
    issues: list[str] = []
    values: dict[str, Any] | None = None

    if status == "empty":
        issues.append(f"No waste record found for {plant} / {period}.")
        result_status = "missing"
    elif status in ("ok", "duplicate"):
        r = rows[0]
        values = {
            "waste_generated_tonnes": r["waste_generated_tonnes"],
            "waste_recycled_tonnes": r["waste_recycled_tonnes"],
            "waste_utilized_tonnes": r["waste_utilized_tonnes"],
        }
        if status == "duplicate":
            issues.append(f"{len(rows)} identical waste records found for {plant} / {period} (logged more than once).")
        if r["waste_recycled_tonnes"] > r["waste_generated_tonnes"]:
            issues.append(
                f"Impossible value: waste_recycled_tonnes ({r['waste_recycled_tonnes']}) exceeds "
                f"waste_generated_tonnes ({r['waste_generated_tonnes']})."
            )
        if r["waste_utilized_tonnes"] > r["waste_generated_tonnes"]:
            issues.append(
                f"Impossible value: waste_utilized_tonnes ({r['waste_utilized_tonnes']}) exceeds "
                f"waste_generated_tonnes ({r['waste_generated_tonnes']})."
            )
        result_status = "ok"
    else:  # conflict
        systems = source_systems(rows)
        issues.append(
            f"{len(rows)} conflicting waste records found for {plant} / {period} "
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
