"""Tool: get_maintenance_data.

Agent-callable wrapper around `app.data.maintenance.MaintenanceDataSource`.
Used by root-cause analysis (Phase 7) to explain a gap -- e.g. missing CEMS
evidence traced to an overdue sensor calibration. Unlike the quarterly
metric tools, `period` is optional here: maintenance events don't align to
quarter boundaries the way production/energy do, so root-cause analysis
usually wants the plant's full maintenance history, not one quarter's slice.
"""

from typing import Any

from app.data.maintenance import MaintenanceDataSource
from app.tools._common import validate_period, validate_plant
from app.tools.schema import ToolParam, ToolSpec

_source = MaintenanceDataSource()

GET_MAINTENANCE_DATA_SPEC = ToolSpec(
    name="get_maintenance_data",
    description=(
        "Retrieve maintenance and instrument-calibration records for a plant, "
        "optionally filtered to one reporting period."
    ),
    inputs=[
        ToolParam("plant", "str", True, "One of the configured plant identifiers."),
        ToolParam("period", "str", False, "A configured fiscal-quarter period; omit for the plant's full history."),
    ],
    output_description=(
        "{status: 'ok'|'no_records', plant, period, records: list[dict], "
        "overdue_count: int, issues: list[str]}. Zero records is a normal, "
        "unremarkable outcome here (not a data-quality flag), unlike the "
        "quarterly metric tools -- an empty maintenance log for a quiet quarter "
        "is expected, not suspicious."
    ),
    raises="ToolInputError if plant is unknown, or period is given and not one of the configured values.",
)


def get_maintenance_data(plant: str, period: str | None = None) -> dict[str, Any]:
    validate_plant(plant)
    if period is not None:
        validate_period(period)

    records = _source.fetch(plant, period)
    overdue = [r for r in records if r["maintenance_status"] == "Overdue"]

    return {
        "status": "ok" if records else "no_records",
        "plant": plant,
        "period": period,
        "records": records,
        "overdue_count": len(overdue),
        "issues": [],
    }
