"""Unit tests for app.reports.scoring: the configurable, category-weighted
readiness score.
"""

import pytest

from app.calculations.scoring import CalculationError
from app.compliance.engine import run_compliance_assessment
from app.reports.scoring import DEFAULT_CATEGORY_WEIGHTS, calculate_weighted_readiness_score


class TestCalculateWeightedReadinessScore:
    def test_default_weights_sum_to_one(self):
        assert abs(sum(DEFAULT_CATEGORY_WEIGHTS.values()) - 1.0) < 1e-9

    def test_returns_overall_score_and_four_category_breakdown(self):
        assessment = run_compliance_assessment("Plant B", "FY2025-26 Q4")
        result = calculate_weighted_readiness_score(assessment)
        assert 0 <= result["overall_score"] <= 100
        assert {c.category for c in result["breakdown"]} == {"Carbon", "Energy", "Evidence", "Data Quality"}

    def test_overall_score_is_the_weighted_sum(self):
        assessment = run_compliance_assessment("Plant B", "FY2025-26 Q4")
        result = calculate_weighted_readiness_score(assessment)
        expected = sum(c.score * c.weight for c in result["breakdown"])
        assert result["overall_score"] == round(expected, 1)

    def test_every_category_carries_a_reason(self):
        assessment = run_compliance_assessment("Plant A", "FY2025-26 Q4")
        result = calculate_weighted_readiness_score(assessment)
        for c in result["breakdown"]:
            assert c.reason
            assert isinstance(c.reason, str)

    def test_configurable_weights_change_the_overall_score(self):
        assessment = run_compliance_assessment("Plant B", "FY2025-26 Q4")
        default = calculate_weighted_readiness_score(assessment)
        carbon_heavy = calculate_weighted_readiness_score(
            assessment, {"Carbon": 0.70, "Energy": 0.10, "Evidence": 0.10, "Data Quality": 0.10}
        )
        assert default["overall_score"] != carbon_heavy["overall_score"]

    def test_weights_not_summing_to_one_raises(self):
        assessment = run_compliance_assessment("Plant A", "FY2025-26 Q4")
        with pytest.raises(CalculationError):
            calculate_weighted_readiness_score(assessment, {"Carbon": 0.5, "Energy": 0.5, "Evidence": 0.5, "Data Quality": 0.5})

    def test_missing_category_raises(self):
        assessment = run_compliance_assessment("Plant A", "FY2025-26 Q4")
        with pytest.raises(CalculationError):
            calculate_weighted_readiness_score(assessment, {"Carbon": 0.5, "Energy": 0.5})

    def test_unknown_category_raises(self):
        assessment = run_compliance_assessment("Plant A", "FY2025-26 Q4")
        with pytest.raises(CalculationError):
            calculate_weighted_readiness_score(
                assessment, {"Carbon": 0.25, "Energy": 0.25, "Evidence": 0.25, "Water": 0.25}
            )

    def test_plant_b_carbon_and_energy_reflect_the_known_gap(self):
        # Plant B's known worsening thermal/emission trend should visibly
        # drag its Carbon and Energy category scores down.
        assessment = run_compliance_assessment("Plant B", "FY2025-26 Q4")
        result = calculate_weighted_readiness_score(assessment)
        by_category = {c.category: c for c in result["breakdown"]}
        assert by_category["Carbon"].score < 100
        assert by_category["Energy"].score < 100
        assert "Potential Gap" in by_category["Carbon"].reason

    def test_clean_data_quality_scores_100(self):
        assessment = run_compliance_assessment("Plant A", "FY2025-26 Q4")
        result = calculate_weighted_readiness_score(assessment)
        by_category = {c.category: c for c in result["breakdown"]}
        assert by_category["Data Quality"].score == 100.0
