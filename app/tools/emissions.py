"""Tool: get_emission_data.

Agent-callable wrapper around `app.data.emissions.EmissionsDataSource`.
"""

from typing import Any

from app.data.emissions import EmissionsDataSource
from app.tools._common import resolve_rows, source_systems, validate_period, validate_plant
from app.tools.schema import ToolParam, ToolSpec

_source = EmissionsDataSource()

GET_EMISSION_DATA_SPEC = ToolSpec(
    name="get_emission_data",
    description="Retrieve Scope 1, Scope 2, and total GHG emissions for one plant and reporting period.",
    inputs=[
        ToolParam("plant", "str", True, "One of the configured plant identifiers."),
        ToolParam("period", "str", True, "A configured fiscal-quarter period."),
    ],
    output_description=(
        "{status: 'ok'|'missing'|'conflict', plant, period, values: dict|None, "
        "issues: list[str], source_system, raw_records}. `issues` flags an "
        "internal arithmetic inconsistency if scope_1 + scope_2 != total."
    ),
    raises="ToolInputError if plant or period is not one of the configured values.",
)


def get_emission_data(plant: str, period: str) -> dict[str, Any]:
    validate_plant(plant)
    validate_period(period)

    rows = _source.fetch(plant, period)
    status = resolve_rows(rows)
    issues: list[str] = []
    values: dict[str, Any] | None = None

    if status == "empty":
        issues.append(f"No emissions record found for {plant} / {period}.")
        result_status = "missing"
    elif status in ("ok", "duplicate"):
        r = rows[0]
        values = {
            "scope_1_tco2e": r["scope_1_tco2e"],
            "scope_2_tco2e": r["scope_2_tco2e"],
            "total_tco2e": r["total_tco2e"],
            "emission_sources": r["emission_sources"],
        }
        if status == "duplicate":
            issues.append(f"{len(rows)} identical emissions records found for {plant} / {period} (logged more than once).")
        if abs((r["scope_1_tco2e"] + r["scope_2_tco2e"]) - r["total_tco2e"]) > 0.5:
            issues.append(
                f"scope_1_tco2e + scope_2_tco2e ({r['scope_1_tco2e'] + r['scope_2_tco2e']}) "
                f"does not match total_tco2e ({r['total_tco2e']})."
            )
        result_status = "ok"
    else:  # conflict
        systems = source_systems(rows)
        issues.append(
            f"{len(rows)} conflicting emissions records found for {plant} / {period} "
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
