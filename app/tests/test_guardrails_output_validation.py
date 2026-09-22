"""Unit tests for app.guardrails.output_validation: guardrail #14."""

from app.guardrails.output_validation import ensure_compliance_disclaimer, validate_output
from app.guardrails.schemas import ActionRequest, GuardrailEvent


class TestValidateOutput:
    def test_none_final_answer_always_passes(self):
        # A safe stop is never a validation failure.
        result = validate_output("Why is Plant B's readiness low?", None, [], human_review_required=False)
        assert result.passed is True

    def test_ordinary_answer_passes(self):
        result = validate_output(
            "What is Plant A's emission intensity?",
            "Plant A's emission intensity for FY2025-26 Q4 is 0.568 tCO2e per tonne cement.",
            [], human_review_required=False,
        )
        assert result.passed is True

    def test_legal_compliance_question_without_hedge_fails(self):
        result = validate_output(
            "Is the plant legally compliant?",
            "Yes, the plant is fully compliant.",
            [], human_review_required=False,
        )
        assert result.passed is False
        assert any("legal-compliance" in v for v in result.violations)
        assert result.safe_response is not None

    def test_legal_compliance_question_with_proper_hedge_passes(self):
        result = validate_output(
            "Is the plant legally compliant?",
            "Based on the regulatory requirements available in the knowledge base, no potential gap "
            "was identified for the assessed requirement. This is a compliance-readiness assessment, "
            "not a determination of legal compliance.",
            [], human_review_required=False,
        )
        assert result.passed is True

    def test_undisclosed_conflict_fails(self):
        events = [GuardrailEvent(guardrail="DATA_CONFLICT", severity="HIGH", reason="x", action="BLOCK_CALCULATION")]
        result = validate_output(
            "What is Plant C's production?", "Plant C produced 181500 tonnes.",
            events, human_review_required=False,
        )
        assert result.passed is False
        assert any("conflict" in v.lower() for v in result.violations)

    def test_disclosed_conflict_with_human_review_flag_passes(self):
        events = [GuardrailEvent(guardrail="DATA_CONFLICT", severity="HIGH", reason="x", action="BLOCK_CALCULATION", human_review_required=True)]
        result = validate_output(
            "What is Plant C's production?", "Data conflict detected; human review required.",
            events, human_review_required=True,
        )
        assert result.passed is True

    def test_claiming_an_unapproved_action_was_executed_fails(self):
        action = ActionRequest(action="submit regulatory report", level="LEVEL_3_CONSEQUENTIAL", description="submit regulatory report", requires_approval=True, approved=False)
        result = validate_output(
            "Submit the regulatory report.", "The report has been submitted to the regulator.",
            [], human_review_required=True, pending_actions=[action],
        )
        assert result.passed is False
        assert any("unapproved" in v.lower() for v in result.violations)

    def test_correctly_deferring_an_unapproved_action_passes(self):
        action = ActionRequest(action="submit regulatory report", level="LEVEL_3_CONSEQUENTIAL", description="submit regulatory report", requires_approval=True, approved=False)
        result = validate_output(
            "Submit the regulatory report.",
            "This action requires explicit human approval before it can proceed.",
            [], human_review_required=True, pending_actions=[action],
        )
        assert result.passed is True


class TestEnsureComplianceDisclaimer:
    def test_appends_disclaimer_when_missing(self):
        text = ensure_compliance_disclaimer("Yes, the plant is compliant.", "Is the plant legally compliant?")
        assert "not a determination of legal compliance" in text

    def test_does_not_duplicate_an_existing_hedge(self):
        original = "Based on the knowledge base, no potential gap was identified; this is not a determination of legal compliance."
        text = ensure_compliance_disclaimer(original, "Is the plant legally compliant?")
        assert text == original

    def test_leaves_unrelated_answers_untouched(self):
        text = ensure_compliance_disclaimer("Plant A produced 452000 tonnes.", "How much did Plant A produce?")
        assert text == "Plant A produced 452000 tonnes."
