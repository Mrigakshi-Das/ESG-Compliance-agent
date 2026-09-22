"""Unit tests for app.guardrails.data_integrity: guardrails #1, #2, #8."""

from app.compliance.data_quality import DataQualityReport
from app.guardrails.data_integrity import (
    build_data_conflict,
    classify_tool_result,
    detect_anomalies,
    score_data_quality,
    tag_provenance,
)


class TestClassifyToolResult:
    def test_none_result_is_data_missing(self):
        assert classify_tool_result("get_production_data", None) == "DATA_MISSING"

    def test_status_missing_is_data_missing(self):
        assert classify_tool_result("get_production_data", {"status": "missing"}) == "DATA_MISSING"

    def test_status_conflict_is_data_conflict(self):
        assert classify_tool_result("get_production_data", {"status": "conflict"}) == "DATA_CONFLICT"

    def test_clean_ok_result_is_data_ok(self):
        result = {"status": "ok", "values": {"clinker_production_tonnes": 305000.0}, "issues": []}
        assert classify_tool_result("get_production_data", result) == "DATA_OK"

    def test_negative_impossible_value_is_data_anomaly(self):
        result = {"status": "ok", "values": {"cement_production_tonnes": -1000.0}, "issues": []}
        assert classify_tool_result("get_production_data", result) == "DATA_ANOMALY"

    def test_out_of_range_percentage_is_data_anomaly(self):
        result = {"status": "ok", "values": {"ash_content_pct": 140.0}, "issues": []}
        assert classify_tool_result("get_fuel_quality_data", result) == "DATA_ANOMALY"

    def test_duplicate_record_issue_is_data_anomaly(self):
        result = {
            "status": "ok", "values": {"clinker_production_tonnes": 305000.0},
            "issues": ["2 identical production records found for Plant A / FY2025-26 Q4 (logged more than once)."],
        }
        assert classify_tool_result("get_production_data", result) == "DATA_ANOMALY"

    def test_bare_calculation_result_is_data_ok(self):
        # calculate_priority-shaped result has no "status" key at all.
        assert classify_tool_result("calculate_priority", {"score": 60.0, "priority": "High"}) == "DATA_OK"


class TestDetectAnomalies:
    def test_negative_production_flagged(self):
        anomalies = detect_anomalies("get_production_data", {"clinker_production_tonnes": -500.0})
        assert anomalies
        assert "negative" in anomalies[0]

    def test_positive_values_not_flagged(self):
        assert detect_anomalies("get_production_data", {"clinker_production_tonnes": 305000.0}) == []

    def test_percentage_over_100_flagged(self):
        anomalies = detect_anomalies("get_energy_data", {"alternative_fuel_thermal_substitution_pct": 250.0})
        assert anomalies


class TestTagProvenance:
    def test_builds_registered_tool_provenance(self):
        result = {"plant": "Plant A", "period": "FY2025-26 Q4"}
        prov = tag_provenance("get_production_data", result)
        assert prov.source == "get_production_data"
        assert prov.source_type == "registered_tool"
        assert prov.plant == "Plant A"
        assert prov.period == "FY2025-26 Q4"
        assert prov.verified is True


class TestBuildDataConflict:
    def test_builds_conflict_with_values_and_sources(self):
        result = {
            "status": "conflict",
            "period": "FY2025-26 Q2",
            "raw_records": [
                {"plant_id": "Plant C", "period": "FY2025-26 Q2", "cement_production_tonnes": 181500.0, "source_system": "SAP_PP"},
                {"plant_id": "Plant C", "period": "FY2025-26 Q2", "cement_production_tonnes": 179800.0, "source_system": "ESG_Portal"},
            ],
        }
        conflict = build_data_conflict("get_production_data", result, metric="cement_production_tonnes")
        assert conflict is not None
        assert conflict.metric == "cement_production_tonnes"
        assert len(conflict.values) == 2
        assert {v.source for v in conflict.values} == {"SAP_PP", "ESG_Portal"}
        assert {v.value for v in conflict.values} == {181500.0, 179800.0}
        assert conflict.severity == "HIGH"
        assert "cannot be reliably used" in conflict.impact

    def test_returns_none_when_not_a_conflict(self):
        assert build_data_conflict("get_production_data", {"status": "ok"}) is None


class TestScoreDataQuality:
    def test_clean_report_scores_100(self):
        report = DataQualityReport(plant="Plant A", period="FY2025-26 Q4")
        score = score_data_quality(report)
        assert score.completeness == 100.0
        assert score.consistency == 100.0
        assert score.timeliness == 100.0
        assert score.overall == 100.0

    def test_missing_domain_reduces_completeness_only(self):
        report = DataQualityReport(plant="Plant C", period="FY2025-26 Q3", missing_domains=["production"])
        score = score_data_quality(report)
        assert score.completeness == 80.0  # 4/5 domains present
        assert score.consistency == 100.0

    def test_conflicting_domain_reduces_consistency(self):
        report = DataQualityReport(plant="Plant C", period="FY2025-26 Q2", conflicting_domains=["production"])
        score = score_data_quality(report)
        assert score.consistency == 80.0

    def test_score_is_never_used_as_a_compliance_proof(self):
        # Structural check: DataQualityScore carries no compliance-related
        # field at all -- it cannot be mistaken for one.
        report = DataQualityReport(plant="Plant A", period="FY2025-26 Q4")
        score = score_data_quality(report)
        assert not hasattr(score, "compliant")
        assert not hasattr(score, "status")
