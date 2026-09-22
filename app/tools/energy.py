"""Tool: get_energy_data.

Agent-callable wrapper around `app.data.energy.EnergyDataSource`. Also
cross-checks the plant's *reported* specific electricity consumption
against the value independently recomputed from raw electricity/production
figures -- catching a future "SAP says X, the meter implies Y" conflict even
though the current synthetic dataset has no such mismatch. Requires
`get_production_data` for the same plant/period to run that check; if
production is unavailable the energy data itself is still returned, just
without the cross-check.
"""

from typing import Any

from app.data.energy import EnergyDataSource
from app.tools._common import resolve_rows, source_systems, validate_period, validate_plant
from app.tools.errors import ToolInputError
from app.tools.schema import ToolParam, ToolSpec

_source = EnergyDataSource()

_SEC_TOLERANCE_PCT = 2.0  # cross-check tolerance: reported vs. recomputed SEC

GET_ENERGY_DATA_SPEC = ToolSpec(
    name="get_energy_data",
    description=(
        "Retrieve electricity, thermal energy, fuel, and renewable energy data "
        "for one plant and reporting period, cross-checked against production."
    ),
    inputs=[
        ToolParam("plant", "str", True, "One of the configured plant identifiers."),
        ToolParam("period", "str", True, "A configured fiscal-quarter period."),
    ],
    output_description=(
        "{status: 'ok'|'missing'|'conflict', plant, period, values: dict|None, "
        "issues: list[str], source_system, raw_records}. `issues` includes a flag "
        "if reported specific electricity consumption disagrees with the value "
        f"recomputed from raw electricity/production by more than {_SEC_TOLERANCE_PCT}%."
    ),
    raises="ToolInputError if plant or period is not one of the configured values.",
)


def get_energy_data(plant: str, period: str) -> dict[str, Any]:
    validate_plant(plant)
    validate_period(period)

    rows = _source.fetch(plant, period)
    status = resolve_rows(rows)
    issues: list[str] = []
    values: dict[str, Any] | None = None

    if status == "empty":
        issues.append(f"No energy record found for {plant} / {period}.")
        result_status = "missing"
    elif status in ("ok", "duplicate"):
        r = rows[0]
        values = {
            "electricity_consumption_mwh": r["electricity_consumption_mwh"],
            "thermal_energy_gj": r["thermal_energy_gj"],
            "fuel_consumption_tonnes": r["fuel_consumption_tonnes"],
            "alternative_fuel_thermal_substitution_pct": r["alternative_fuel_thermal_substitution_pct"],
            "renewable_energy_mwh": r["renewable_energy_mwh"],
            "specific_electricity_consumption_kwh_per_t_cement": r["specific_electricity_consumption_kwh_per_t_cement"],
            "specific_thermal_energy_consumption_gj_per_t_clinker": r["specific_thermal_energy_consumption_gj_per_t_clinker"],
        }
        if status == "duplicate":
            issues.append(f"{len(rows)} identical energy records found for {plant} / {period} (logged more than once).")
        issues += _cross_check_sec(plant, period, r)
        result_status = "ok"
    else:  # conflict
        systems = source_systems(rows)
        issues.append(
            f"{len(rows)} conflicting energy records found for {plant} / {period} "
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


def _cross_check_sec(plant: str, period: str, energy_row: dict[str, Any]) -> list[str]:
    # Imported lazily to avoid a hard import cycle at module load time
    # (production.py does not import energy.py, but keeping the dependency
    # local documents that this check is optional, not structural).
    from app.tools.production import get_production_data

    try:
        production = get_production_data(plant, period)
    except ToolInputError:
        return []
    if production["status"] != "ok":
        return [f"Could not cross-check specific electricity consumption: production data is {production['status']} for {plant} / {period}."]

    cement_tonnes = production["values"]["cement_production_tonnes"]
    recomputed = energy_row["electricity_consumption_mwh"] * 1000 / cement_tonnes
    reported = energy_row["specific_electricity_consumption_kwh_per_t_cement"]
    if reported == 0:
        return []
    pct_diff = abs(recomputed - reported) / reported * 100
    if pct_diff > _SEC_TOLERANCE_PCT:
        return [
            f"Reported specific electricity consumption ({reported} kWh/t cement) differs from "
            f"the value recomputed from raw electricity/production ({recomputed:.2f} kWh/t cement) "
            f"by {pct_diff:.1f}%, exceeding the {_SEC_TOLERANCE_PCT}% tolerance."
        ]
    return []
