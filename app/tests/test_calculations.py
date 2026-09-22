"""Unit tests for the deterministic calculation tools: valid input,
invalid input, and boundary conditions. No dataset involved -- these are
pure functions.
"""

import pytest

from app.calculations.emissions import calculate_emission_intensity
from app.calculations.energy import calculate_energy_intensity
from app.calculations.errors import CalculationError
from app.calculations.scoring import calculate_priority, compare_with_target


class TestCalculateEmissionIntensity:
    def test_valid_input(self):
        assert calculate_emission_intensity(100_000, 50_000) == pytest.approx(2.0)

    def test_zero_production_raises(self):
        with pytest.raises(CalculationError):
            calculate_emission_intensity(100_000, 0)

    def test_negative_production_raises(self):
        with pytest.raises(CalculationError):
            calculate_emission_intensity(100_000, -1)

    def test_negative_emissions_raises(self):
        with pytest.raises(CalculationError):
            calculate_emission_intensity(-1, 100_000)

    def test_zero_emissions_is_valid(self):
        # boundary: zero emissions is physically implausible for a cement
        # kiln but not undefined -- the function should not reject it.
        assert calculate_emission_intensity(0, 100_000) == 0.0


class TestCalculateEnergyIntensity:
    def test_valid_input(self):
        assert calculate_energy_intensity(1000, 500) == pytest.approx(2.0)

    def test_zero_production_raises(self):
        with pytest.raises(CalculationError):
            calculate_energy_intensity(1000, 0)

    def test_negative_energy_raises(self):
        with pytest.raises(CalculationError):
            calculate_energy_intensity(-1, 1000)


class TestCompareWithTarget:
    def test_lower_is_better_within_target(self):
        result = compare_with_target(2.9, 3.0, "Specific Thermal Energy Consumption")
        assert result["status"] == "Within Target"
        assert result["variance"] == pytest.approx(-0.1)
        assert result["percentage_variance"] == pytest.approx(-3.333333, rel=1e-4)

    def test_lower_is_better_exceeds_target(self):
        result = compare_with_target(3.9, 3.4, "Specific Thermal Energy Consumption")
        assert result["status"] == "Exceeds Target"
        assert result["percentage_variance"] == pytest.approx(14.7058, rel=1e-3)

    def test_higher_is_better_below_target(self):
        result = compare_with_target(0.05, 0.10, "Renewable Energy Share", direction="higher_is_better")
        assert result["status"] == "Below Target"

    def test_higher_is_better_within_target(self):
        result = compare_with_target(0.15, 0.10, "Renewable Energy Share", direction="higher_is_better")
        assert result["status"] == "Within Target"

    def test_exact_match_is_within_target(self):
        # boundary: actual == target must count as compliant, not exceeding.
        result = compare_with_target(3.0, 3.0, "metric")
        assert result["status"] == "Within Target"
        assert result["variance"] == 0
        assert result["percentage_variance"] == 0

    def test_zero_target_raises(self):
        with pytest.raises(CalculationError):
            compare_with_target(1.0, 0, "metric")

    def test_non_numeric_target_raises(self):
        # e.g. a qualitative BRSR disclosure requirement passed by mistake
        with pytest.raises(CalculationError):
            compare_with_target(1.0, "Mandatory disclosure", "metric")

    def test_invalid_direction_raises(self):
        with pytest.raises(CalculationError):
            compare_with_target(1.0, 2.0, "metric", direction="sideways")


class TestCalculatePriority:
    def test_valid_input(self):
        result = calculate_priority(5, 4, 4)
        assert result["score"] == pytest.approx(80.0)
        assert result["priority"] == "Critical"

    def test_low_priority_boundary(self):
        result = calculate_priority(1, 1, 1)
        assert result["score"] == pytest.approx(1.0)
        assert result["priority"] == "Low"

    def test_band_boundaries_are_inclusive(self):
        assert calculate_priority(4, 4, 5)["priority"] == "Critical"  # score == 80
        assert calculate_priority(2, 4, 5)["priority"] == "High"  # score == 40
        assert calculate_priority(1, 3, 5)["priority"] == "Medium"  # score == 15
        assert calculate_priority(1, 3, 4.9)["priority"] == "Low"  # score == 14.7

    def test_out_of_range_raises(self):
        with pytest.raises(CalculationError):
            calculate_priority(6, 4, 4)
        with pytest.raises(CalculationError):
            calculate_priority(0, 4, 4)

    def test_non_numeric_raises(self):
        with pytest.raises(CalculationError):
            calculate_priority("high", 4, 4)
