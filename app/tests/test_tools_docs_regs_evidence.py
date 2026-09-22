"""Unit tests for search_documents, search_regulations, and assess_evidence."""

import pytest

from app.tools.documents import search_documents
from app.tools.errors import ToolInputError
from app.tools.evidence import assess_evidence
from app.tools.regulations import search_regulations


class TestSearchDocuments:
    def test_valid_input(self):
        result = search_documents("Plant A", document_type="BRSR Annual Report")
        assert result["status"] == "ok"
        assert len(result["documents"]) == 2

    def test_invalid_plant_raises(self):
        with pytest.raises(ToolInputError):
            search_documents("Plant Z")

    def test_invalid_period_raises(self):
        with pytest.raises(ToolInputError):
            search_documents("Plant A", period="not-a-period")

    def test_no_records_is_not_an_error(self):
        result = search_documents("Plant A", document_type="Nonexistent Document Type")
        assert result["status"] == "no_records"
        assert result["documents"] == []

    def test_duplicate_document_id_is_flagged(self):
        # KNOWN_DATA_ISSUES.md #3: DOC-C-2026-014 appears twice for Plant C.
        result = search_documents("Plant C", document_type="CEMS Calibration")
        assert result["status"] == "ok"
        assert result["duplicate_document_ids"] == ["DOC-C-2026-014"]
        assert "duplicate record" in result["issues"][0]

    def test_period_filters_to_covering_documents(self):
        # DOC-A-2025-004 (CEMS cert, valid 2025-07-20 to 2026-01-20) should
        # cover FY2025-26 Q3 (Oct-Dec 2025) but not FY2024-25 Q3.
        covering = search_documents("Plant A", document_type="CEMS Calibration", period="FY2025-26 Q3")
        ids = {d["document_id"] for d in covering["documents"]}
        assert "DOC-A-2025-004" in ids
        not_covering = search_documents("Plant A", document_type="CEMS Calibration", period="FY2024-25 Q3")
        ids = {d["document_id"] for d in not_covering["documents"]}
        assert "DOC-A-2025-004" not in ids


class TestSearchRegulations:
    def test_valid_input(self):
        result = search_regulations("emission")
        assert result["status"] == "ok"
        assert any("CCTS" in r["regulation"] for r in result["regulations"])
        assert "compliance readiness assessment" in result["notice"].lower()
        assert "legal compliance" in result["notice"].lower()

    def test_no_matches_is_not_an_error(self):
        result = search_regulations("xyz-nonexistent-topic")
        assert result["status"] == "no_matches"
        assert result["regulations"] == []

    def test_blank_topic_raises(self):
        with pytest.raises(ToolInputError):
            search_regulations("   ")

    def test_unsupported_industry_raises(self):
        with pytest.raises(ToolInputError):
            search_regulations("emission", industry="steel")

    def test_reporting_period_filter(self):
        result = search_regulations("CCTS", reporting_period="FY2025-26")
        assert result["status"] == "ok"
        assert result["regulations"]
        assert all("FY2025-26" in r["reporting_period"] for r in result["regulations"])

    def test_finds_pat_and_brsr_core(self):
        pat = search_regulations("PAT")
        assert any(r["requirement_id"].startswith("BEE-PAT") for r in pat["regulations"])
        core = search_regulations("BRSR Core")
        assert any(r["requirement_id"].startswith("SEBI-BRSRCORE") for r in core["regulations"])

    def test_every_regulation_has_a_source(self):
        result = search_regulations("cement")
        for r in result["regulations"]:
            assert r["source_title"]
            assert r["source_url"]
            assert r["source_date"]

    def test_potentially_outdated_flag_present(self):
        result = search_regulations("BRSR")
        assert result["regulations"]
        for r in result["regulations"]:
            assert isinstance(r["potentially_outdated"], bool)


class TestAssessEvidence:
    def test_compliant(self):
        docs = search_documents("Plant A", document_type="BRSR Annual Report")["documents"]
        result = assess_evidence({"required_document_types": ["BRSR Annual Report"]}, docs)
        assert result["evidence_status"] == "Compliant"
        assert result["missing_evidence"] == []

    def test_missing(self):
        result = assess_evidence({"required_document_types": ["Water Consent to Operate"]}, [])
        assert result["evidence_status"] == "Missing"
        assert result["missing_evidence"] == ["Water Consent to Operate"]

    def test_outdated(self):
        # Plant B's Environmental Clearance is expired (KNOWN_DATA_ISSUES.md #4).
        docs = search_documents("Plant B", document_type="Environmental Clearance")["documents"]
        result = assess_evidence({"required_document_types": ["Environmental Clearance"]}, docs)
        assert result["evidence_status"] == "Outdated"
        assert len(result["outdated_evidence"]) == 1

    def test_conflicting(self):
        # Plant C's duplicated CEMS certificate (KNOWN_DATA_ISSUES.md #3).
        docs = search_documents("Plant C", document_type="CEMS Calibration")["documents"]
        result = assess_evidence({"required_document_types": ["CEMS Calibration Certificate"]}, docs)
        assert result["evidence_status"] == "Conflicting"

    def test_mixed_when_partially_covered(self):
        docs = search_documents("Plant A", document_type="BRSR Annual Report")["documents"]
        result = assess_evidence(
            {"required_document_types": ["BRSR Annual Report", "Water Consent to Operate"]}, docs
        )
        assert result["evidence_status"] == "Mixed"
        assert result["missing_evidence"] == ["Water Consent to Operate"]
        assert len(result["matched_evidence"]) == 1

    def test_empty_required_types_raises(self):
        with pytest.raises(ToolInputError):
            assess_evidence({"required_document_types": []}, [])

    def test_bad_as_of_date_raises(self):
        with pytest.raises(ToolInputError):
            assess_evidence({"required_document_types": ["x"], "as_of_date": "not-a-date"}, [])
