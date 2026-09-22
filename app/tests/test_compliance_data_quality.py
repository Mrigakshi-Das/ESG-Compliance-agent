"""Unit tests for app.compliance.data_quality: the standalone data-quality
engine, run against the real Phase 2 dataset's known issues.
"""

from app.compliance.data_quality import assess_data_quality


class TestAssessDataQuality:
    def test_clean_period_reports_clean(self):
        report = assess_data_quality("Plant A", "FY2025-26 Q4")
        assert report.overall == "Clean"
        assert report.missing_domains == []
        assert report.conflicting_domains == []

    def test_known_missing_production_period(self):
        # KNOWN_DATA_ISSUES.md #1: Plant C, FY2025-26 Q3. Plant C also has a
        # duplicated evidence document (#3) that isn't period-specific, so
        # it's visible for every Plant C query -- "Conflicts Found" is the
        # correct overall verdict here since a conflict outranks a mere gap.
        report = assess_data_quality("Plant C", "FY2025-26 Q3")
        assert "production" in report.missing_domains
        assert report.overall == "Conflicts Found"

    def test_known_conflicting_production_period(self):
        # KNOWN_DATA_ISSUES.md #2: Plant C, FY2025-26 Q2.
        report = assess_data_quality("Plant C", "FY2025-26 Q2")
        assert "production" in report.conflicting_domains
        assert report.overall == "Conflicts Found"

    def test_known_impossible_waste_value_is_flagged(self):
        # KNOWN_DATA_ISSUES.md #7: Plant B, FY2025-26 Q3.
        report = assess_data_quality("Plant B", "FY2025-26 Q3")
        assert "waste" in report.flagged_issues
        assert any("Impossible value" in i for i in report.flagged_issues["waste"])

    def test_duplicate_documents_flagged_as_conflict(self):
        # KNOWN_DATA_ISSUES.md #3: Plant C's duplicated CEMS certificate is
        # visible regardless of which period is queried (it's a document
        # repository issue, not a quarterly metric).
        report = assess_data_quality("Plant C", "FY2025-26 Q4")
        assert "DOC-C-2026-014" in report.duplicate_documents
        assert report.overall == "Conflicts Found"

    def test_report_is_plant_and_period_specific(self):
        report = assess_data_quality("Plant B", "FY2025-26 Q4")
        assert report.plant == "Plant B"
        assert report.period == "FY2025-26 Q4"
