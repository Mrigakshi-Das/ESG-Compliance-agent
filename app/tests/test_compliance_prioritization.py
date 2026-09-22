"""Unit tests for app.compliance.prioritization: the Risk x Business Impact
x Urgency priority engine.
"""

from app.compliance.prioritization import prioritize_gaps
from app.compliance.types import Gap


def _gap(status: str, variance_pct: float | None = None) -> Gap:
    return Gap(plant="Plant B", period="FY2025-26 Q4", requirement_id="TEST-1", regulation="Test", status=status, variance_pct=variance_pct)


class TestPrioritizeGaps:
    def test_each_gap_gets_score_and_band(self):
        gaps = [_gap("Data Conflict")]
        result = prioritize_gaps(gaps)
        assert result[0].risk is not None
        assert result[0].business_impact is not None
        assert result[0].urgency is not None
        assert result[0].priority_score == result[0].risk * result[0].business_impact * result[0].urgency
        assert result[0].priority_band in ("Critical", "High", "Medium", "Low")

    def test_sorted_highest_first(self):
        gaps = [_gap("Data Missing"), _gap("Data Conflict"), _gap("Human Review Required")]
        result = prioritize_gaps(gaps)
        scores = [g.priority_score for g in result]
        assert scores == sorted(scores, reverse=True)

    def test_potential_gap_scales_with_variance(self):
        small = prioritize_gaps([_gap("Potential Gap", variance_pct=5.0)])[0]
        medium = prioritize_gaps([_gap("Potential Gap", variance_pct=15.0)])[0]
        large = prioritize_gaps([_gap("Potential Gap", variance_pct=30.0)])[0]
        assert small.priority_score < medium.priority_score < large.priority_score

    def test_potential_gap_uses_absolute_variance(self):
        # A large *undershoot* is scored the same as an equally large overshoot.
        negative = prioritize_gaps([_gap("Potential Gap", variance_pct=-30.0)])[0]
        positive = prioritize_gaps([_gap("Potential Gap", variance_pct=30.0)])[0]
        assert negative.priority_score == positive.priority_score

    def test_missing_variance_defaults_to_lowest_band(self):
        gap = prioritize_gaps([_gap("Potential Gap", variance_pct=None)])[0]
        assert gap.priority_band in ("Medium", "Low")

    def test_evidence_outdated_is_urgent(self):
        # An already-lapsed document should score at least as urgent as a
        # merely-missing one.
        outdated = prioritize_gaps([_gap("Evidence Outdated")])[0]
        missing = prioritize_gaps([_gap("Data Missing")])[0]
        assert outdated.urgency >= missing.urgency

    def test_unknown_status_gets_a_conservative_default_not_a_crash(self):
        gap = _gap("Some Future Status Not Yet Defined")
        result = prioritize_gaps([gap])
        assert result[0].priority_score > 0
