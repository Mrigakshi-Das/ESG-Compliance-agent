"""Unit tests for app.guardrails.confidence: guardrail #13 -- a
transparent methodology, never a bare LLM-claimed number."""

from app.guardrails.confidence import assess_confidence


class TestAssessConfidence:
    def test_all_factors_met_is_high(self):
        result = assess_confidence(
            data_statuses=["DATA_OK", "DATA_OK"],
            evidence_statuses=["EVIDENCE_VERIFIED"],
            regulatory_statuses=["CURRENT"],
            calculation_statuses=["PASSED"],
            source_tiers=["TIER_1_AUTHORITATIVE"],
        )
        assert result.level == "HIGH"
        assert all(f.met for f in result.factors)
        assert result.human_review_recommended is False

    def test_no_signals_at_all_defaults_high(self):
        # Nothing was checked (e.g. a pure regulatory lookup with no
        # numeric claim) -- vacuously all factors are "met" since none
        # were violated, not a penalized state.
        result = assess_confidence()
        assert result.level == "HIGH"

    def test_data_conflict_caps_confidence_at_low(self):
        result = assess_confidence(data_statuses=["DATA_CONFLICT"])
        assert result.level == "LOW"
        assert result.human_review_recommended is True

    def test_data_missing_caps_confidence_at_low(self):
        result = assess_confidence(data_statuses=["DATA_MISSING"])
        assert result.level == "LOW"

    def test_missing_evidence_caps_confidence_at_low(self):
        result = assess_confidence(evidence_statuses=["EVIDENCE_MISSING"])
        assert result.level == "LOW"

    def test_blocked_calculation_caps_confidence_at_low(self):
        result = assess_confidence(calculation_statuses=["BLOCKED"])
        assert result.level == "LOW"

    def test_non_critical_gap_is_medium_not_low(self):
        # A stale regulatory record (UNKNOWN, not OUTDATED) with everything
        # else fine is a real limitation but not the kind that makes the
        # whole conclusion untrustworthy.
        result = assess_confidence(
            data_statuses=["DATA_OK"],
            regulatory_statuses=["UNKNOWN"],
        )
        assert result.level == "MEDIUM"

    def test_methodology_is_a_real_documented_string_not_a_guess(self):
        result = assess_confidence()
        assert "HIGH requires" in result.methodology
        assert len(result.methodology) > 50

    def test_factors_are_individually_inspectable(self):
        result = assess_confidence(data_statuses=["DATA_CONFLICT"])
        names = {f.name for f in result.factors}
        assert names == {
            "Source authority", "Data integrity", "Evidence completeness",
            "Regulatory certainty", "Calculation validation",
        }
        data_factor = next(f for f in result.factors if f.name == "Data integrity")
        assert data_factor.met is False
