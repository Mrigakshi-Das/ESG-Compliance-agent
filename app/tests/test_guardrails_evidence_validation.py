"""Unit tests for app.guardrails.evidence_validation: guardrail #7 --
critically, "no evidence != compliant"."""

from app.guardrails.evidence_validation import build_evidence_finding, classify_evidence_status, safe_evidence_statement


class TestClassifyEvidenceStatus:
    def test_compliant_maps_to_verified(self):
        assert classify_evidence_status("Compliant") == "EVIDENCE_VERIFIED"

    def test_missing_maps_to_evidence_missing(self):
        assert classify_evidence_status("Missing") == "EVIDENCE_MISSING"

    def test_outdated_maps_to_evidence_outdated(self):
        assert classify_evidence_status("Outdated") == "EVIDENCE_OUTDATED"

    def test_conflicting_maps_to_evidence_conflict(self):
        assert classify_evidence_status("Conflicting") == "EVIDENCE_CONFLICT"

    def test_mixed_is_not_verified(self):
        # Partial coverage must never render as fully verified.
        assert classify_evidence_status("Mixed") != "EVIDENCE_VERIFIED"

    def test_unrecognized_status_is_evidence_invalid(self):
        assert classify_evidence_status("Something Weird") == "EVIDENCE_INVALID"


class TestBuildEvidenceFinding:
    def test_missing_evidence_requires_human_review_and_low_confidence(self):
        finding = build_evidence_finding(
            "Kiln CEMS calibration certificate",
            {"evidence_status": "Missing"},
            assessment_period="FY2025-26 Q4",
        )
        assert finding.evidence_status == "EVIDENCE_MISSING"
        assert finding.human_review_required is True
        assert finding.confidence == "LOW"

    def test_verified_evidence_does_not_require_review(self):
        finding = build_evidence_finding(
            "BRSR Annual Report",
            {"evidence_status": "Compliant"},
            assessment_period="FY2025-26 Q4",
        )
        assert finding.evidence_status == "EVIDENCE_VERIFIED"
        assert finding.human_review_required is False
        assert finding.confidence == "HIGH"

    def test_no_evidence_never_produces_a_compliant_reading(self):
        # The critical rule, stated as a direct assertion: for every
        # non-"Compliant" raw status, the resulting finding is never
        # EVIDENCE_VERIFIED and always flags for human review.
        for raw_status in ("Missing", "Outdated", "Conflicting", "Mixed", ""):
            finding = build_evidence_finding("Some evidence", {"evidence_status": raw_status}, "FY2025-26 Q4")
            assert finding.evidence_status != "EVIDENCE_VERIFIED"
            assert finding.human_review_required is True


class TestSafeEvidenceStatement:
    def test_missing_evidence_statement_never_claims_compliance(self):
        finding = build_evidence_finding("Calibration", {"evidence_status": "Missing"}, "FY2025-26 Q4")
        statement = safe_evidence_statement(finding, "Calibration")
        assert "compliant" not in statement.lower()
        assert "cannot be verified" in statement.lower()
        assert "was not found" in statement.lower()

    def test_verified_evidence_statement_is_positive(self):
        finding = build_evidence_finding("BRSR Report", {"evidence_status": "Compliant"}, "FY2025-26 Q4")
        statement = safe_evidence_statement(finding, "BRSR Report")
        assert "verified" in statement.lower()
