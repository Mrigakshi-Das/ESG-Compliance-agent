"""Unit tests for get_historical_metric and compare_plants."""

import pytest

from app.tools.analytics import compare_plants, get_historical_metric
from app.tools.errors import ToolInputError


class TestGetHistoricalMetric:
    def test_valid_input_increasing_trend(self):
        result = get_historical_metric("Plant B", "specific_thermal_energy_consumption_gj_per_t_clinker")
        assert result["trend"] == "increasing"
        assert len(result["series"]) == 6
        assert all(s["status"] == "ok" for s in result["series"])

    def test_decreasing_trend_beyond_tolerance(self):
        result = get_historical_metric("Plant A", "specific_thermal_energy_consumption_gj_per_t_clinker")
        # Plant A improves gradually (3.05 -> 2.95), a ~3.3% decrease --
        # just outside the 2% "flat" tolerance, so this should read decreasing.
        assert result["trend"] == "decreasing"

    def test_derived_metric_propagates_missing_and_conflict(self):
        result = get_historical_metric("Plant C", "emission_intensity_tco2e_per_t_cement")
        by_period = {s["period"]: s for s in result["series"]}
        assert by_period["FY2025-26 Q3"]["status"] == "missing"
        assert by_period["FY2025-26 Q2"]["status"] == "conflict"
        assert by_period["FY2025-26 Q4"]["status"] == "ok"

    def test_invalid_plant_raises(self):
        with pytest.raises(ToolInputError):
            get_historical_metric("Plant Z", "total_tco2e")

    def test_invalid_metric_raises(self):
        with pytest.raises(ToolInputError):
            get_historical_metric("Plant A", "not_a_real_metric")

    def test_custom_period_subset(self):
        result = get_historical_metric("Plant A", "total_tco2e", periods=["FY2025-26 Q3", "FY2025-26 Q4"])
        assert len(result["series"]) == 2

    def test_insufficient_data_with_single_ok_period(self):
        result = get_historical_metric("Plant C", "cement_production_tonnes", periods=["FY2025-26 Q4"])
        assert result["trend"] == "insufficient_data"


class TestComparePlants:
    def test_valid_input_ranks_lower_is_better_ascending(self):
        result = compare_plants("emission_intensity_tco2e_per_t_cement", "FY2025-26 Q4")
        assert result["ranked"] == ["Plant A", "Plant C", "Plant B"]
        assert result["unavailable_plants"] == []

    def test_higher_is_better_ranks_descending(self):
        result = compare_plants("cement_production_tonnes", "FY2025-26 Q4")
        assert result["direction"] == "higher_is_better"
        assert result["ranked"][0] == "Plant A"  # highest production first

    def test_excludes_unavailable_plant_from_ranking(self):
        result = compare_plants("clinker_production_tonnes", "FY2025-26 Q3")
        assert "Plant C" in result["unavailable_plants"]
        assert "Plant C" not in result["ranked"]
        assert set(result["ranked"]) == {"Plant A", "Plant B"}

    def test_invalid_period_raises(self):
        with pytest.raises(ToolInputError):
            compare_plants("total_tco2e", "not-a-period")

    def test_custom_plant_subset(self):
        result = compare_plants("total_tco2e", "FY2025-26 Q4", plants=["Plant A", "Plant B"])
        assert set(r["plant"] for r in result["results"]) == {"Plant A", "Plant B"}
