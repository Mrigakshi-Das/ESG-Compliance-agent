"""Unit tests for the eight domain data tools: get_production_data,
get_energy_data, get_emission_data, get_water_data, get_waste_data,
get_fuel_quality_data, get_weather_data, get_maintenance_data.

Covers valid input, invalid input, missing data, conflicting data, and
boundary/impossible-value conditions, against both the real Phase 2
dataset (where it already contains the case) and monkeypatched data (where
it's a tool-logic case the current dataset doesn't happen to exercise).
"""

import pytest

from app.tools import energy as energy_tool
from app.tools import emissions as emissions_tool
from app.tools import water as water_tool
from app.tools.emissions import get_emission_data
from app.tools.energy import _cross_check_sec, get_energy_data
from app.tools.errors import ToolInputError
from app.tools.fuel_quality import get_fuel_quality_data
from app.tools.maintenance import get_maintenance_data
from app.tools.production import get_production_data
from app.tools.waste import get_waste_data
from app.tools.water import get_water_data
from app.tools.weather import get_weather_data


class TestGetProductionData:
    def test_valid_input(self):
        result = get_production_data("Plant A", "FY2025-26 Q4")
        assert result["status"] == "ok"
        assert result["values"] == {
            "clinker_production_tonnes": 305000.0,
            "cement_production_tonnes": 452000.0,
            "operating_days": 90,
        }
        assert result["issues"] == []

    def test_invalid_plant_raises(self):
        with pytest.raises(ToolInputError):
            get_production_data("Plant Z", "FY2025-26 Q4")

    def test_invalid_period_raises(self):
        with pytest.raises(ToolInputError):
            get_production_data("Plant A", "FY1999-00 Q1")

    def test_missing_data(self):
        result = get_production_data("Plant C", "FY2025-26 Q3")
        assert result["status"] == "missing"
        assert result["values"] is None
        assert result["raw_records"] == []
        assert "No production record found" in result["issues"][0]

    def test_conflicting_data(self):
        result = get_production_data("Plant C", "FY2025-26 Q2")
        assert result["status"] == "conflict"
        assert result["values"] is None
        assert len(result["raw_records"]) == 2
        assert set(result["source_system"]) == {"SAP_PP", "ESG_Portal"}
        assert "conflicting production records" in result["issues"][0]


class TestGetEnergyData:
    def test_valid_input(self):
        result = get_energy_data("Plant A", "FY2024-25 Q3")
        assert result["status"] == "ok"
        assert result["values"]["electricity_consumption_mwh"] == pytest.approx(33755.0)
        assert result["values"]["thermal_energy_gj"] == pytest.approx(890600.0)
        assert result["issues"] == []

    def test_invalid_plant_raises(self):
        with pytest.raises(ToolInputError):
            get_energy_data("Plant Z", "FY2024-25 Q3")

    def test_available_even_when_production_is_missing(self):
        # Plant C FY2025-26 Q3 has no production record, but energy meters
        # kept running -- see KNOWN_DATA_ISSUES.md #1.
        result = get_energy_data("Plant C", "FY2025-26 Q3")
        assert result["status"] == "ok"

    def test_sec_cross_check_flags_mismatch(self, monkeypatch):
        # The real dataset has no SEC mismatch, so exercise the tool's own
        # cross-check logic directly with a deliberately wrong reported SEC.
        energy_row = {
            "electricity_consumption_mwh": 34352.0,
            "specific_electricity_consumption_kwh_per_t_cement": 999.0,  # wildly wrong
        }
        issues = _cross_check_sec("Plant A", "FY2025-26 Q4", energy_row)
        assert len(issues) == 1
        assert "differs from" in issues[0]

    def test_sec_cross_check_passes_for_consistent_data(self):
        result = get_energy_data("Plant A", "FY2025-26 Q4")
        assert result["issues"] == []  # reported SEC matches recomputed SEC


class TestGetEmissionData:
    def test_valid_input(self):
        result = get_emission_data("Plant B", "FY2025-26 Q4")
        assert result["status"] == "ok"
        assert result["values"]["scope_1_tco2e"] == pytest.approx(191100.0)
        assert result["values"]["scope_2_tco2e"] == pytest.approx(16083.1)
        assert result["values"]["total_tco2e"] == pytest.approx(207183.1)

    def test_invalid_period_raises(self):
        with pytest.raises(ToolInputError):
            get_emission_data("Plant B", "not-a-period")

    def test_arithmetic_inconsistency_is_flagged(self, monkeypatch):
        bad_row = {
            "plant_id": "Plant A",
            "period": "FY2025-26 Q4",
            "scope_1_tco2e": 100.0,
            "scope_2_tco2e": 50.0,
            "total_tco2e": 999.0,  # deliberately inconsistent
            "emission_sources": "test",
            "source_system": "test",
        }
        monkeypatch.setattr(emissions_tool._source, "fetch", lambda plant, period: [bad_row])
        result = get_emission_data("Plant A", "FY2025-26 Q4")
        assert result["status"] == "ok"  # a single record was still found
        assert any("does not match total_tco2e" in i for i in result["issues"])


class TestGetWaterData:
    def test_valid_input(self):
        result = get_water_data("Plant A", "FY2025-26 Q1")
        assert result["status"] == "ok"
        assert result["values"]["water_withdrawal_m3"] == pytest.approx(144000)

    def test_impossible_value_is_flagged(self, monkeypatch):
        bad_row = {
            "plant_id": "Plant A",
            "period": "FY2025-26 Q1",
            "water_withdrawal_m3": 1000.0,
            "water_consumption_m3": 5000.0,  # impossible: exceeds withdrawal
            "recycled_water_m3": 200.0,
            "water_intensity_m3_per_t_cement": 0.01,
            "source_system": "test",
        }
        monkeypatch.setattr(water_tool._source, "fetch", lambda plant, period: [bad_row])
        result = get_water_data("Plant A", "FY2025-26 Q1")
        assert result["status"] == "ok"
        assert any("Impossible value" in i for i in result["issues"])


class TestGetWasteData:
    def test_valid_input(self):
        result = get_waste_data("Plant A", "FY2024-25 Q3")
        assert result["status"] == "ok"
        assert result["issues"] == []

    def test_known_impossible_value_in_real_dataset(self):
        # KNOWN_DATA_ISSUES.md #7: Plant B FY2025-26 Q3, recycled > generated.
        result = get_waste_data("Plant B", "FY2025-26 Q3")
        assert result["status"] == "ok"
        assert result["values"]["waste_recycled_tonnes"] > result["values"]["waste_generated_tonnes"]
        assert any("Impossible value" in i and "waste_recycled_tonnes" in i for i in result["issues"])

    def test_boundary_recycled_equals_generated_is_not_flagged(self, monkeypatch):
        from app.tools import waste as waste_tool

        boundary_row = {
            "plant_id": "Plant A",
            "period": "FY2025-26 Q1",
            "waste_generated_tonnes": 500.0,
            "waste_recycled_tonnes": 500.0,  # exactly equal -- not impossible
            "waste_utilized_tonnes": 0.0,
            "source_system": "test",
        }
        monkeypatch.setattr(waste_tool._source, "fetch", lambda plant, period: [boundary_row])
        result = get_waste_data("Plant A", "FY2025-26 Q1")
        assert result["issues"] == []


class TestGetMaintenanceData:
    def test_valid_input_full_history(self):
        result = get_maintenance_data("Plant B")
        assert result["status"] == "ok"
        assert len(result["records"]) == 3
        assert result["overdue_count"] == 2

    def test_valid_input_filtered_by_period(self):
        result = get_maintenance_data("Plant B", "FY2025-26 Q2")
        assert result["status"] == "ok"
        assert len(result["records"]) == 2
        assert result["overdue_count"] == 1

    def test_no_records_is_not_an_error(self):
        result = get_maintenance_data("Plant A", "FY2024-25 Q4")
        assert result["status"] == "no_records"
        assert result["records"] == []

    def test_invalid_plant_raises(self):
        with pytest.raises(ToolInputError):
            get_maintenance_data("Plant Z")

    def test_invalid_period_raises(self):
        with pytest.raises(ToolInputError):
            get_maintenance_data("Plant B", "not-a-period")


class TestGetFuelQualityData:
    def test_valid_input(self):
        result = get_fuel_quality_data("Plant B", "FY2024-25 Q3")
        assert result["status"] == "ok"
        assert result["values"] == {
            "gross_calorific_value_kcal_per_kg": 4780.0,
            "ash_content_pct": 17.5,
            "moisture_content_pct": 8.0,
            "sulphur_content_pct": 0.88,
        }
        assert result["issues"] == []

    def test_shows_the_deliberate_quality_decline(self):
        # Plant B's fuel quality genuinely degrades over the 6 quarters --
        # the new correlation gap_analysis.py's external-factor scan relies on.
        first = get_fuel_quality_data("Plant B", "FY2024-25 Q3")["values"]
        last = get_fuel_quality_data("Plant B", "FY2025-26 Q4")["values"]
        assert last["gross_calorific_value_kcal_per_kg"] < first["gross_calorific_value_kcal_per_kg"]
        assert last["ash_content_pct"] > first["ash_content_pct"]

    def test_invalid_plant_raises(self):
        with pytest.raises(ToolInputError):
            get_fuel_quality_data("Plant Z", "FY2025-26 Q4")

    def test_invalid_period_raises(self):
        with pytest.raises(ToolInputError):
            get_fuel_quality_data("Plant A", "not-a-period")


class TestGetWeatherData:
    def test_valid_input(self):
        result = get_weather_data("Plant A", "FY2025-26 Q2")
        assert result["status"] == "ok"
        assert result["values"] == {
            "avg_ambient_temp_c": 31.0,
            "rainfall_mm": 650.0,
            "avg_humidity_pct": 78.0,
        }
        assert result["issues"] == []

    def test_invalid_plant_raises(self):
        with pytest.raises(ToolInputError):
            get_weather_data("Plant Z", "FY2025-26 Q4")

    def test_invalid_period_raises(self):
        with pytest.raises(ToolInputError):
            get_weather_data("Plant A", "not-a-period")
