"""Tests for app.reports.report_generator (the 13-section assembly) and
app.reports.renderers (JSON/Markdown/PDF export).
"""

import json
import os

from app.compliance.engine import run_compliance_assessment
from app.reports.report_generator import generate_compliance_report
from app.reports.renderers import render_json, render_markdown, render_pdf

_REQUIRED_SECTIONS_IN_MARKDOWN = [
    "Executive Summary", "Overall ESG Readiness Score", "KPI Dashboard",
    "Applicable Regulatory Requirements", "Compliance Status", "Key Gaps",
    "Root-Cause Analysis", "Priority Actions", "Evidence Status",
    "Data Quality Issues", "Assumptions", "Sources", "Human Review Required",
]


class TestGenerateComplianceReport:
    def test_builds_from_scratch(self):
        report = generate_compliance_report("Plant B", "FY2025-26 Q4")
        assert report.plant == "Plant B"
        assert report.period == "FY2025-26 Q4"

    def test_reuses_a_precomputed_assessment(self):
        assessment = run_compliance_assessment("Plant B", "FY2025-26 Q4")
        report = generate_compliance_report("Plant B", "FY2025-26 Q4", assessment=assessment)
        assert report.compliance_status == assessment.requirement_statuses

    def test_disclaimer_present_and_correct(self):
        report = generate_compliance_report("Plant A", "FY2025-26 Q4")
        assert "not a determination of legal compliance" in report.disclaimer

    def test_executive_summary_is_specific_not_generic(self):
        # Management language: must name the actual plant, score, and top
        # gap -- not a template that could apply to any company.
        report = generate_compliance_report("Plant B", "FY2025-26 Q4")
        assert "Plant B" in report.executive_summary
        assert str(report.readiness_score["overall_score"]) in report.executive_summary

    def test_key_gaps_sorted_by_priority(self):
        report = generate_compliance_report("Plant B", "FY2025-26 Q4")
        scores = [g.priority_score for g in report.key_gaps]
        assert scores == sorted(scores, reverse=True)

    def test_root_cause_only_for_gaps_with_investigation(self):
        report = generate_compliance_report("Plant B", "FY2025-26 Q4")
        investigated_ids = {rc.requirement_id for rc in report.root_cause_analysis}
        gap_ids_with_root_cause = {g.requirement_id for g in report.key_gaps if g.root_cause}
        assert investigated_ids == gap_ids_with_root_cause

    def test_hypothesis_confidence_survives_into_the_report(self):
        # A finding's High/Medium/Low confidence (app.compliance.gap_analysis)
        # must reach the report, not be silently dropped when facts and
        # hypotheses are split out of the raw findings list.
        report = generate_compliance_report("Plant B", "FY2025-26 Q4")
        all_hypotheses = [h for rc in report.root_cause_analysis for h in rc.hypotheses]
        assert all_hypotheses
        for h in all_hypotheses:
            assert h.confidence in ("High", "Medium", "Low")
        assert any("Kiln Refractory Lining" in h.statement for h in all_hypotheses)

    def test_sources_only_cover_applicable_requirements(self):
        report = generate_compliance_report("Plant A", "FY2025-26 Q4")
        cited_requirement_ids = {rid for s in report.sources for rid in s.cited_by}
        assert cited_requirement_ids.issubset(set(report.compliance_status))

    def test_human_review_required_matches_status_table(self):
        report = generate_compliance_report("Plant B", "FY2025-26 Q4")
        expected = {rid for rid, s in report.compliance_status.items() if s == "Human Review Required"}
        actual = {h["requirement_id"] for h in report.human_review_required}
        assert expected == actual

    def test_custom_category_weights_are_honored(self):
        default_report = generate_compliance_report("Plant B", "FY2025-26 Q4")
        custom_report = generate_compliance_report(
            "Plant B", "FY2025-26 Q4",
            category_weights={"Carbon": 0.10, "Energy": 0.10, "Evidence": 0.10, "Data Quality": 0.70},
        )
        assert default_report.readiness_score["overall_score"] != custom_report.readiness_score["overall_score"]


class TestRenderJson:
    def test_round_trips_as_valid_json(self):
        report = generate_compliance_report("Plant A", "FY2025-26 Q4")
        data = json.loads(render_json(report))
        assert data["plant"] == "Plant A"
        assert "readiness_score" in data
        assert "key_gaps" in data

    def test_no_data_class_objects_leak_through(self):
        # every nested dataclass (Gap, KPIEntry, CategoryScore, etc.) must
        # serialize to a plain dict/list/primitive.
        report = generate_compliance_report("Plant B", "FY2025-26 Q4")
        text = render_json(report)
        assert "object at 0x" not in text


class TestRenderMarkdown:
    def test_contains_all_thirteen_sections(self):
        report = generate_compliance_report("Plant B", "FY2025-26 Q4")
        md = render_markdown(report)
        for section in _REQUIRED_SECTIONS_IN_MARKDOWN:
            assert section in md, f"Missing section: {section}"

    def test_hypothesis_confidence_is_rendered(self):
        report = generate_compliance_report("Plant B", "FY2025-26 Q4")
        md = render_markdown(report)
        assert "confidence)" in md

    def test_is_specific_not_generic_esg_language(self):
        report = generate_compliance_report("Plant B", "FY2025-26 Q4")
        md = render_markdown(report)
        assert "Plant B" in md
        assert "Kiln Refractory Lining" in md  # the actual sourced root cause, not a platitude

    def test_readiness_score_table_shows_weight_score_reason(self):
        report = generate_compliance_report("Plant A", "FY2025-26 Q4")
        md = render_markdown(report)
        assert "| Category | Weight | Score | Reason |" in md

    def test_disclaimer_present(self):
        report = generate_compliance_report("Plant A", "FY2025-26 Q4")
        md = render_markdown(report)
        assert "not a determination of legal compliance" in md


class TestRenderPdf:
    def test_produces_a_valid_pdf_file(self, tmp_path):
        report = generate_compliance_report("Plant B", "FY2025-26 Q4")
        path = tmp_path / "report.pdf"
        render_pdf(report, str(path))
        assert path.exists()
        assert path.stat().st_size > 1000
        with open(path, "rb") as f:
            assert f.read(5) == b"%PDF-"

    def test_handles_plant_with_no_gaps_gracefully(self, tmp_path):
        # Exercise the "no gaps"/"no root cause" empty-state text paths.
        report = generate_compliance_report("Plant A", "FY2025-26 Q4")
        path = tmp_path / "report_a.pdf"
        render_pdf(report, str(path))
        assert os.path.getsize(path) > 1000
