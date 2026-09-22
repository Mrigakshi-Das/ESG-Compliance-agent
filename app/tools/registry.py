"""Aggregates every tool's `ToolSpec` into one inventory the future planner
(Phase 6) can inspect to decide which tools a given request needs, without
importing every tool module individually. Also doubles as the definitive
tool list for documentation/testing.

Calculation tools (calculate_emission_intensity, calculate_energy_intensity,
compare_with_target, calculate_priority) are deliberately included here too,
even though they live in `app.calculations` rather than `app.tools` --
from the agent's perspective they are callable tools like any other; the
package split is an internal implementation detail (deterministic math vs.
data retrieval), not something the planner needs to know about.
"""

from app.calculations.emissions import calculate_emission_intensity
from app.calculations.energy import calculate_energy_intensity
from app.calculations.scoring import calculate_priority, compare_with_target
from app.tools.analytics import COMPARE_PLANTS_SPEC, GET_HISTORICAL_METRIC_SPEC, compare_plants, get_historical_metric
from app.tools.documents import SEARCH_DOCUMENTS_SPEC, search_documents
from app.tools.emissions import GET_EMISSION_DATA_SPEC, get_emission_data
from app.tools.energy import GET_ENERGY_DATA_SPEC, get_energy_data
from app.tools.evidence import ASSESS_EVIDENCE_SPEC, assess_evidence
from app.tools.fuel_quality import GET_FUEL_QUALITY_DATA_SPEC, get_fuel_quality_data
from app.tools.maintenance import GET_MAINTENANCE_DATA_SPEC, get_maintenance_data
from app.tools.production import GET_PRODUCTION_DATA_SPEC, get_production_data
from app.tools.regulations import SEARCH_REGULATIONS_SPEC, search_regulations
from app.tools.schema import ToolParam, ToolSpec
from app.tools.waste import GET_WASTE_DATA_SPEC, get_waste_data
from app.tools.water import GET_WATER_DATA_SPEC, get_water_data
from app.tools.weather import GET_WEATHER_DATA_SPEC, get_weather_data

CALCULATE_EMISSION_INTENSITY_SPEC = ToolSpec(
    name="calculate_emission_intensity",
    description="Deterministically compute tCO2e per tonne of production.",
    inputs=[
        ToolParam("emissions_tco2e", "float", True, "Total GHG emissions in tCO2e."),
        ToolParam("production_tonnes", "float", True, "Production in tonnes (must be > 0)."),
    ],
    output_description="float: emissions_tco2e / production_tonnes.",
    raises="CalculationError if production_tonnes <= 0 or emissions_tco2e < 0.",
)

CALCULATE_ENERGY_INTENSITY_SPEC = ToolSpec(
    name="calculate_energy_intensity",
    description="Deterministically compute energy consumed per tonne of production.",
    inputs=[
        ToolParam("energy_consumption", "float", True, "Energy consumed, in the caller's chosen unit."),
        ToolParam("production_tonnes", "float", True, "Production in tonnes (must be > 0)."),
    ],
    output_description="float: energy_consumption / production_tonnes.",
    raises="CalculationError if production_tonnes <= 0 or energy_consumption < 0.",
)

COMPARE_WITH_TARGET_SPEC = ToolSpec(
    name="compare_with_target",
    description="Deterministically compute variance, percentage variance, and a target verdict.",
    inputs=[
        ToolParam("actual", "float", True, "The measured/calculated value."),
        ToolParam("target", "float", True, "The regulatory or internal target (must be numeric and non-zero)."),
        ToolParam("metric", "str", True, "Label for the metric being compared, carried through to the output."),
        ToolParam("direction", "str", False, "'lower_is_better' (default) or 'higher_is_better'."),
    ],
    output_description="{metric, actual, target, variance, percentage_variance, status: 'Within Target'|'Exceeds Target'|'Below Target'}.",
    raises="CalculationError if target == 0, actual/target are not numeric, or direction is invalid.",
)

CALCULATE_PRIORITY_SPEC = ToolSpec(
    name="calculate_priority",
    description="Deterministically compute a Risk x Business Impact x Urgency priority score and band.",
    inputs=[
        ToolParam("risk", "float", True, "1-5."),
        ToolParam("business_impact", "float", True, "1-5."),
        ToolParam("urgency", "float", True, "1-5."),
    ],
    output_description="{score: float (1-125), priority: 'Critical'|'High'|'Medium'|'Low'}.",
    raises="CalculationError if any factor is missing, non-numeric, or outside [1, 5].",
)

TOOL_REGISTRY: dict[str, tuple[ToolSpec, object]] = {
    spec.name: (spec, fn)
    for spec, fn in [
        (SEARCH_REGULATIONS_SPEC, search_regulations),
        (GET_PRODUCTION_DATA_SPEC, get_production_data),
        (GET_ENERGY_DATA_SPEC, get_energy_data),
        (GET_EMISSION_DATA_SPEC, get_emission_data),
        (GET_WATER_DATA_SPEC, get_water_data),
        (GET_WASTE_DATA_SPEC, get_waste_data),
        (GET_FUEL_QUALITY_DATA_SPEC, get_fuel_quality_data),
        (GET_WEATHER_DATA_SPEC, get_weather_data),
        (GET_MAINTENANCE_DATA_SPEC, get_maintenance_data),
        (SEARCH_DOCUMENTS_SPEC, search_documents),
        (CALCULATE_EMISSION_INTENSITY_SPEC, calculate_emission_intensity),
        (CALCULATE_ENERGY_INTENSITY_SPEC, calculate_energy_intensity),
        (COMPARE_WITH_TARGET_SPEC, compare_with_target),
        (ASSESS_EVIDENCE_SPEC, assess_evidence),
        (CALCULATE_PRIORITY_SPEC, calculate_priority),
        (GET_HISTORICAL_METRIC_SPEC, get_historical_metric),
        (COMPARE_PLANTS_SPEC, compare_plants),
    ]
}
