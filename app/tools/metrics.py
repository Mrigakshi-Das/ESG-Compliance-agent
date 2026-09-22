"""Shared metric registry used by `get_historical_metric` and `compare_plants`
(`app.tools.analytics`).

Each entry maps a metric name either to a field already returned by one of
the get_*_data tools, or (for "derived" metrics) to a function that composes
two tool calls and a deterministic calculation. Centralizing this avoids the
two analytics tools duplicating "how do I get this number" logic, and it is
the only place a derived metric touches `app.calculations` directly.
"""

from dataclasses import dataclass
from typing import Any, Callable, Literal

from app.calculations.emissions import calculate_emission_intensity
from app.calculations.energy import calculate_energy_intensity
from app.tools.emissions import get_emission_data
from app.tools.energy import get_energy_data
from app.tools.errors import ToolInputError
from app.tools.fuel_quality import get_fuel_quality_data
from app.tools.production import get_production_data
from app.tools.water import get_water_data
from app.tools.waste import get_waste_data
from app.tools.weather import get_weather_data

Direction = Literal["lower_is_better", "higher_is_better"]


@dataclass(frozen=True)
class MetricValue:
    value: float | None
    status: Literal["ok", "missing", "conflict"]
    issues: list[str]
    unit: str


@dataclass(frozen=True)
class MetricSpec:
    unit: str
    direction: Direction
    fetch: Callable[[str, str], MetricValue]


def _direct(tool_fn: Callable[[str, str], dict[str, Any]], field: str, unit: str) -> Callable[[str, str], MetricValue]:
    def fetch(plant: str, period: str) -> MetricValue:
        result = tool_fn(plant, period)
        if result["status"] != "ok":
            return MetricValue(None, result["status"], result["issues"], unit)
        return MetricValue(result["values"][field], "ok", result["issues"], unit)

    return fetch


def _emission_intensity(plant: str, period: str) -> MetricValue:
    production = get_production_data(plant, period)
    emissions = get_emission_data(plant, period)
    issues = list(production["issues"]) + list(emissions["issues"])
    if production["status"] != "ok" or emissions["status"] != "ok":
        status = "missing" if "missing" in (production["status"], emissions["status"]) else "conflict"
        return MetricValue(None, status, issues, "tCO2e/t cement")
    value = calculate_emission_intensity(
        emissions["values"]["total_tco2e"], production["values"]["cement_production_tonnes"]
    )
    return MetricValue(value, "ok", issues, "tCO2e/t cement")


def _energy_intensity(plant: str, period: str) -> MetricValue:
    production = get_production_data(plant, period)
    energy = get_energy_data(plant, period)
    issues = list(production["issues"]) + list(energy["issues"])
    if production["status"] != "ok" or energy["status"] != "ok":
        status = "missing" if "missing" in (production["status"], energy["status"]) else "conflict"
        return MetricValue(None, status, issues, "kWh/t cement")
    value = calculate_energy_intensity(
        energy["values"]["electricity_consumption_mwh"] * 1000, production["values"]["cement_production_tonnes"]
    )
    return MetricValue(value, "ok", issues, "kWh/t cement")


METRIC_REGISTRY: dict[str, MetricSpec] = {
    "clinker_production_tonnes": MetricSpec("tonnes", "higher_is_better", _direct(get_production_data, "clinker_production_tonnes", "tonnes")),
    "cement_production_tonnes": MetricSpec("tonnes", "higher_is_better", _direct(get_production_data, "cement_production_tonnes", "tonnes")),
    "electricity_consumption_mwh": MetricSpec("MWh", "lower_is_better", _direct(get_energy_data, "electricity_consumption_mwh", "MWh")),
    "thermal_energy_gj": MetricSpec("GJ", "lower_is_better", _direct(get_energy_data, "thermal_energy_gj", "GJ")),
    "specific_electricity_consumption_kwh_per_t_cement": MetricSpec(
        "kWh/t cement", "lower_is_better",
        _direct(get_energy_data, "specific_electricity_consumption_kwh_per_t_cement", "kWh/t cement"),
    ),
    "specific_thermal_energy_consumption_gj_per_t_clinker": MetricSpec(
        "GJ/t clinker", "lower_is_better",
        _direct(get_energy_data, "specific_thermal_energy_consumption_gj_per_t_clinker", "GJ/t clinker"),
    ),
    "scope_1_tco2e": MetricSpec("tCO2e", "lower_is_better", _direct(get_emission_data, "scope_1_tco2e", "tCO2e")),
    "scope_2_tco2e": MetricSpec("tCO2e", "lower_is_better", _direct(get_emission_data, "scope_2_tco2e", "tCO2e")),
    "total_tco2e": MetricSpec("tCO2e", "lower_is_better", _direct(get_emission_data, "total_tco2e", "tCO2e")),
    "water_intensity_m3_per_t_cement": MetricSpec(
        "m3/t cement", "lower_is_better", _direct(get_water_data, "water_intensity_m3_per_t_cement", "m3/t cement")
    ),
    "waste_generated_tonnes": MetricSpec("tonnes", "lower_is_better", _direct(get_waste_data, "waste_generated_tonnes", "tonnes")),
    "emission_intensity_tco2e_per_t_cement": MetricSpec("tCO2e/t cement", "lower_is_better", _emission_intensity),
    "energy_intensity_kwh_per_t_cement": MetricSpec("kWh/t cement", "lower_is_better", _energy_intensity),
    # Added for Phase 6 root-cause investigation, which walks a
    # production -> electricity -> thermal energy -> fuel -> maintenance
    # chain; the first four of those need a historical series each.
    "fuel_consumption_tonnes": MetricSpec("tonnes", "lower_is_better", _direct(get_energy_data, "fuel_consumption_tonnes", "tonnes")),
    "alternative_fuel_thermal_substitution_pct": MetricSpec(
        "%", "higher_is_better", _direct(get_energy_data, "alternative_fuel_thermal_substitution_pct", "%")
    ),
    # Added for the broadened root-cause investigation (gap_analysis.py's
    # _EXTERNAL_FACTOR_CHAIN) -- fuel-quality and weather signals that sit
    # outside the original production/electricity/thermal/fuel/maintenance
    # chain but are still real, correlatable, grounded data.
    "gross_calorific_value_kcal_per_kg": MetricSpec(
        "kcal/kg", "higher_is_better", _direct(get_fuel_quality_data, "gross_calorific_value_kcal_per_kg", "kcal/kg")
    ),
    "ash_content_pct": MetricSpec("%", "lower_is_better", _direct(get_fuel_quality_data, "ash_content_pct", "%")),
    "moisture_content_pct": MetricSpec("%", "lower_is_better", _direct(get_fuel_quality_data, "moisture_content_pct", "%")),
    "sulphur_content_pct": MetricSpec("%", "lower_is_better", _direct(get_fuel_quality_data, "sulphur_content_pct", "%")),
    "avg_ambient_temp_c": MetricSpec("degC", "lower_is_better", _direct(get_weather_data, "avg_ambient_temp_c", "degC")),
    "rainfall_mm": MetricSpec("mm", "lower_is_better", _direct(get_weather_data, "rainfall_mm", "mm")),
    "avg_humidity_pct": MetricSpec("%", "lower_is_better", _direct(get_weather_data, "avg_humidity_pct", "%")),
}


def fetch_metric_value(plant: str, period: str, metric: str) -> MetricValue:
    if metric not in METRIC_REGISTRY:
        raise ToolInputError(f"Unknown metric {metric!r}. Expected one of {sorted(METRIC_REGISTRY)}.")
    return METRIC_REGISTRY[metric].fetch(plant, period)
