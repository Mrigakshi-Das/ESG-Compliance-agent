"""Unit tests for app.guardrails.calculation_safety: guardrail #6."""

from app.calculations.emissions import calculate_emission_intensity
from app.guardrails.calculation_safety import check_input_compatibility, safe_calculate
from app.guardrails.schemas import Provenance


def _prov(plant="Plant A", period="FY2025-26 Q4", source="get_production_data"):
    return Provenance(source=source, source_type="registered_tool", plant=plant, period=period)


class TestCheckInputCompatibility:
    def test_matching_plant_and_period_is_compatible(self):
        inputs = {"a": _prov(), "b": _prov(source="get_emission_data")}
        assert check_input_compatibility(inputs) is None

    def test_mismatched_period_is_flagged(self):
        inputs = {"a": _prov(period="FY2025-26 Q4"), "b": _prov(period="FY2025-26 Q3")}
        reason = check_input_compatibility(inputs)
        assert reason is not None
        assert "reporting periods" in reason

    def test_mismatched_plant_is_flagged(self):
        inputs = {"a": _prov(plant="Plant A"), "b": _prov(plant="Plant B")}
        reason = check_input_compatibility(inputs)
        assert reason is not None
        assert "plants" in reason


class TestSafeCalculate:
    def test_valid_calculation_passes_with_full_structure(self):
        result = safe_calculate(
            calculate_emission_intensity,
            formula="emission_intensity = total_tco2e / cement_production_tonnes",
            units="tCO2e/t cement",
            inputs={"emissions_tco2e": 256663.7, "production_tonnes": 452000.0},
            provenance={"emissions_tco2e": _prov(source="get_emission_data"), "production_tonnes": _prov(source="get_production_data")},
        )
        assert result.validation_status == "PASSED"
        assert result.result is not None
        assert abs(result.result - 256663.7 / 452000.0) < 1e-9
        assert result.formula.startswith("emission_intensity")
        assert result.units == "tCO2e/t cement"
        assert len(result.source_provenance) == 2
        assert result.rejection_reason is None

    def test_negative_production_is_blocked_not_computed(self):
        result = safe_calculate(
            calculate_emission_intensity,
            formula="emission_intensity = total_tco2e / cement_production_tonnes",
            units="tCO2e/t cement",
            inputs={"emissions_tco2e": 1000.0, "production_tonnes": -500.0},
            provenance={"emissions_tco2e": _prov(), "production_tonnes": _prov()},
        )
        assert result.validation_status == "BLOCKED"
        assert result.result is None
        assert "must be > 0" in result.rejection_reason

    def test_zero_production_division_by_zero_is_blocked(self):
        result = safe_calculate(
            calculate_emission_intensity,
            formula="emission_intensity = total_tco2e / cement_production_tonnes",
            units="tCO2e/t cement",
            inputs={"emissions_tco2e": 1000.0, "production_tonnes": 0.0},
            provenance={"emissions_tco2e": _prov(), "production_tonnes": _prov()},
        )
        assert result.validation_status == "BLOCKED"

    def test_negative_emissions_is_blocked(self):
        result = safe_calculate(
            calculate_emission_intensity,
            formula="emission_intensity = total_tco2e / cement_production_tonnes",
            units="tCO2e/t cement",
            inputs={"emissions_tco2e": -100.0, "production_tonnes": 452000.0},
            provenance={"emissions_tco2e": _prov(), "production_tonnes": _prov()},
        )
        assert result.validation_status == "BLOCKED"
        assert "negative" in result.rejection_reason

    def test_incompatible_periods_blocked_before_calculation_runs(self):
        result = safe_calculate(
            calculate_emission_intensity,
            formula="emission_intensity = total_tco2e / cement_production_tonnes",
            units="tCO2e/t cement",
            inputs={"emissions_tco2e": 1000.0, "production_tonnes": 452000.0},
            provenance={
                "emissions_tco2e": _prov(period="FY2025-26 Q4"),
                "production_tonnes": _prov(period="FY2025-26 Q1"),
            },
        )
        assert result.validation_status == "BLOCKED"
        assert "reporting periods" in result.rejection_reason
        assert result.result is None
