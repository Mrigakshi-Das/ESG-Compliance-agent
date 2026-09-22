"""Tool: get_water_data.

Agent-callable wrapper around `app.data.water.WaterDataSource`.
"""

from typing import Any

from app.data.water import WaterDataSource
from app.tools._common import resolve_rows, source_systems, validate_period, validate_plant
from app.tools.schema import ToolParam, ToolSpec

_source = WaterDataSource()

GET_WATER_DATA_SPEC = ToolSpec(
    name="get_water_data",
    description="Retrieve water withdrawal, consumption, recycling, and intensity for one plant and reporting period.",
    inputs=[
        ToolParam("plant", "str", True, "One of the configured plant identifiers."),
        ToolParam("period", "str", True, "A configured fiscal-quarter period."),
    ],
    output_description=(
        "{status: 'ok'|'missing'|'conflict', plant, period, values: dict|None, "
        "issues: list[str], source_system, raw_records}. `issues` flags an "
        "impossible value if consumption or recycled water exceeds withdrawal."
    ),
    raises="ToolInputError if plant or period is not one of the configured values.",
)


def get_water_data(plant: str, period: str) -> dict[str, Any]:
    validate_plant(plant)
    validate_period(period)

    rows = _source.fetch(plant, period)
    status = resolve_rows(rows)
    issues: list[str] = []
    values: dict[str, Any] | None = None

    if status == "empty":
        issues.append(f"No water record found for {plant} / {period}.")
        result_status = "missing"
    elif status in ("ok", "duplicate"):
        r = rows[0]
        values = {
            "water_withdrawal_m3": r["water_withdrawal_m3"],
            "water_consumption_m3": r["water_consumption_m3"],
            "recycled_water_m3": r["recycled_water_m3"],
            "water_intensity_m3_per_t_cement": r["water_intensity_m3_per_t_cement"],
        }
        if status == "duplicate":
            issues.append(f"{len(rows)} identical water records found for {plant} / {period} (logged more than once).")
        if r["water_consumption_m3"] > r["water_withdrawal_m3"]:
            issues.append(
                f"Impossible value: water_consumption_m3 ({r['water_consumption_m3']}) exceeds "
                f"water_withdrawal_m3 ({r['water_withdrawal_m3']})."
            )
        if r["recycled_water_m3"] > r["water_withdrawal_m3"]:
            issues.append(
                f"Impossible value: recycled_water_m3 ({r['recycled_water_m3']}) exceeds "
                f"water_withdrawal_m3 ({r['water_withdrawal_m3']})."
            )
        result_status = "ok"
    else:  # conflict
        systems = source_systems(rows)
        issues.append(
            f"{len(rows)} conflicting water records found for {plant} / {period} "
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
