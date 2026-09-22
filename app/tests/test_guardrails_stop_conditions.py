"""Unit tests for app.guardrails.stop_conditions: guardrail #12."""

from app.guardrails.stop_conditions import classify_and_check, should_stop


class TestShouldStop:
    def test_nothing_wrong_does_not_stop(self):
        decision = should_stop()
        assert decision.should_stop is False
        assert decision.reason is None

    def test_missing_data_stops(self):
        decision = should_stop(required_data_missing=True)
        assert decision.should_stop is True
        assert "unavailable" in decision.reason

    def test_critical_conflict_stops(self):
        decision = should_stop(critical_data_conflict=True)
        assert decision.should_stop is True
        assert "conflict" in decision.reason.lower()

    def test_unvalidated_regulatory_source_stops(self):
        decision = should_stop(regulatory_source_unvalidated=True)
        assert decision.should_stop is True

    def test_failed_calculation_validation_stops(self):
        decision = should_stop(calculation_validation_failed=True)
        assert decision.should_stop is True

    def test_insufficient_evidence_stops(self):
        decision = should_stop(evidence_insufficient=True)
        assert decision.should_stop is True

    def test_action_requiring_authorization_stops(self):
        decision = should_stop(action_requires_authorization=True)
        assert decision.should_stop is True
        assert "authorization" in decision.reason.lower()


class TestClassifyAndCheck:
    def test_all_data_ok_does_not_stop(self):
        decision = classify_and_check(["DATA_OK", "DATA_OK"])
        assert decision.should_stop is False

    def test_data_anomaly_alone_does_not_force_a_stop(self):
        # An anomaly is flagged, not automatically fatal -- guardrails
        # should block only what is genuinely unreliable.
        decision = classify_and_check(["DATA_ANOMALY"])
        assert decision.should_stop is False

    def test_data_missing_forces_a_stop(self):
        decision = classify_and_check(["DATA_OK", "DATA_MISSING"])
        assert decision.should_stop is True

    def test_data_conflict_forces_a_stop(self):
        decision = classify_and_check(["DATA_CONFLICT"])
        assert decision.should_stop is True
