"""Builds the report's KPI Dashboard: the plant's headline operational
figures for the period, each carrying its own data-quality status so a
missing or conflicting reading is shown as such rather than blanked out or
guessed at.

Deliberately broader than `app.compliance.engine`'s gap analysis -- it
includes water and waste, which have no Phase 4 regulatory requirement yet
(by design; see the Phase 1 architecture note on future ESG categories),
because a KPI dashboard should show the plant's real operating picture
whether or not a matching regulation currently exists for it.
"""

from dataclasses import dataclass
from typing import Any

from app.compliance.engine import find_illustrative_target
from app.tools.emissions import get_emission_data
from app.tools.energy import get_energy_data
from app.tools.metrics import fetch_metric_value
from app.tools.production import get_production_data
from app.tools.waste import get_waste_data
from app.tools.water import get_water_data


@dataclass
class KPIEntry:
    name: str
    value: float | None
    unit: str
    target: float | None
    target_is_illustrative: bool
    status: str  # "Within Target" | "Exceeds Target" | "No Target Configured" | "Data Missing" | "Data Conflict"
    data_status: str  # "ok" | "missing" | "conflict"


def _metric_kpi(name: str, metric_key: str, unit: str, target_label: str | None, plant: str, period: str) -> KPIEntry:
    mv = fetch_metric_value(plant, period, metric_key)
    if mv.status != "ok":
        return KPIEntry(name, None, unit, None, False, "Data Missing" if mv.status == "missing" else "Data Conflict", mv.status)

    target = find_illustrative_target(plant, target_label) if target_label else None
    if target is None:
        return KPIEntry(name, round(mv.value, 4), unit, None, False, "No Target Configured", "ok")

    status = "Within Target" if mv.value <= target else "Exceeds Target"
    return KPIEntry(name, round(mv.value, 4), unit, target, True, status, "ok")


def build_kpi_dashboard(plant: str, period: str) -> list[KPIEntry]:
    entries: list[KPIEntry] = [
        _metric_kpi("Clinker Production", "clinker_production_tonnes", "tonnes", None, plant, period),
        _metric_kpi("Cement Production", "cement_production_tonnes", "tonnes", None, plant, period),
        _metric_kpi(
            "Specific Thermal Energy Consumption", "specific_thermal_energy_consumption_gj_per_t_clinker",
            "GJ/t clinker", "Specific Thermal Energy Consumption", plant, period,
        ),
        _metric_kpi(
            "Specific Electricity Consumption", "specific_electricity_consumption_kwh_per_t_cement",
            "kWh/t cement", None, plant, period,
        ),
        _metric_kpi("Scope 1 Emissions", "scope_1_tco2e", "tCO2e", None, plant, period),
        _metric_kpi("Scope 2 Emissions", "scope_2_tco2e", "tCO2e", None, plant, period),
        _metric_kpi("Total GHG Emissions", "total_tco2e", "tCO2e", None, plant, period),
        _metric_kpi(
            "Emission Intensity", "emission_intensity_tco2e_per_t_cement", "tCO2e/t cement",
            "GHG Emission Intensity", plant, period,
        ),
        _metric_kpi("Water Intensity", "water_intensity_m3_per_t_cement", "m3/t cement", None, plant, period),
        _metric_kpi("Waste Generated", "waste_generated_tonnes", "tonnes", None, plant, period),
    ]

    renewable_entry = _renewable_share_kpi(plant, period)
    if renewable_entry:
        entries.insert(4, renewable_entry)

    return entries


def _renewable_share_kpi(plant: str, period: str) -> KPIEntry | None:
    energy = get_energy_data(plant, period)
    if energy["status"] != "ok":
        return KPIEntry("Renewable Energy Share", None, "%", None, False, "Data Missing" if energy["status"] == "missing" else "Data Conflict", energy["status"])
    electricity = energy["values"]["electricity_consumption_mwh"]
    renewable = energy["values"]["renewable_energy_mwh"]
    share = round(renewable / electricity * 100, 1) if electricity else 0.0
    return KPIEntry("Renewable Energy Share", share, "%", None, False, "No Target Configured", "ok")


def raw_domain_snapshot(plant: str, period: str) -> dict[str, Any]:
    """The unprocessed get_*_data results behind the dashboard, for
    traceability -- every KPI number should be attributable back to one of
    these tool calls."""
    return {
        "production": get_production_data(plant, period),
        "energy": get_energy_data(plant, period),
        "emissions": get_emission_data(plant, period),
        "water": get_water_data(plant, period),
        "waste": get_waste_data(plant, period),
    }
