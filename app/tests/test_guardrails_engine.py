"""Unit tests for app.guardrails.engine.GuardrailEngine -- the object that
ties every guardrail module together and owns the per-run event log."""

from app.calculations.emissions import calculate_emission_intensity
from app.guardrails.engine import GuardrailEngine
from app.guardrails.schemas import Provenance


class TestCheckToolResult:
    def test_clean_result_logs_nothing(self):
        eng = GuardrailEngine()
        status = eng.check_tool_result("get_production_data", {"status": "ok", "values": {"clinker_production_tonnes": 305000.0}, "issues": []})
        assert status == "DATA_OK"
        assert eng.events == []

    def test_missing_result_logs_an_event(self):
        eng = GuardrailEngine()
        status = eng.check_tool_result("get_production_data", {"status": "missing", "issues": []})
        assert status == "DATA_MISSING"
        assert len(eng.events) == 1
        assert eng.events[0].guardrail == "DATA_MISSING"
        assert eng.events[0].severity == "HIGH"

    def test_conflict_result_logs_an_event_and_requires_human_review(self):
        eng = GuardrailEngine()
        result = {
            "status": "conflict", "period": "FY2025-26 Q2",
            "raw_records": [
                {"cement_production_tonnes": 181500.0, "source_system": "SAP_PP"},
                {"cement_production_tonnes": 179800.0, "source_system": "ESG_Portal"},
            ],
        }
        status = eng.check_tool_result("get_production_data", result)
        assert status == "DATA_CONFLICT"
        assert eng.human_review_required is True
        assert "SAP_PP" in eng.events[0].sources


class TestCheckCalculation:
    def test_passed_calculation_recorded(self):
        eng = GuardrailEngine()
        prov = Provenance(source="get_production_data", source_type="registered_tool", plant="Plant A", period="FY2025-26 Q4")
        result = eng.check_calculation(
            calculate_emission_intensity, "emission_intensity = total_tco2e / cement_production_tonnes",
            "tCO2e/t cement", {"emissions_tco2e": 100.0, "production_tonnes": 200.0},
            {"emissions_tco2e": prov, "production_tonnes": prov},
        )
        assert result.validation_status == "PASSED"
        assert eng.events == []

    def test_blocked_calculation_logs_an_event(self):
        eng = GuardrailEngine()
        prov = Provenance(source="get_production_data", source_type="registered_tool")
        result = eng.check_calculation(
            calculate_emission_intensity, "emission_intensity = total_tco2e / cement_production_tonnes",
            "tCO2e/t cement", {"emissions_tco2e": 100.0, "production_tonnes": -1.0},
            {"emissions_tco2e": prov, "production_tonnes": prov},
        )
        assert result.validation_status == "BLOCKED"
        assert any(e.guardrail == "CALCULATION_BLOCKED" for e in eng.events)


class TestCheckAction:
    def test_level_1_action_logs_nothing(self):
        eng = GuardrailEngine()
        action = eng.check_action("retrieve production data")
        assert action.requires_approval is False
        assert eng.events == []
        assert eng.approval_required is False

    def test_level_3_action_logs_and_flags_approval_required(self):
        eng = GuardrailEngine()
        action = eng.check_action("submit the regulatory report to CPCB")
        assert action.requires_approval is True
        assert eng.approval_required is True
        assert eng.human_review_required is True
        assert any(e.guardrail == "ACTION_REQUIRES_APPROVAL" for e in eng.events)
        assert action in eng.pending_actions


class TestDashboard:
    def test_dashboard_reflects_recorded_signals(self):
        eng = GuardrailEngine()
        eng.check_evidence("Calibration cert", {"evidence_status": "Missing"}, "FY2025-26 Q4")
        dash = eng.dashboard()
        assert dash["evidence_coverage_pct"] == 0.0
        assert dash["human_review_required"] is True
        assert dash["total_events"] == 1

    def test_empty_run_dashboard_is_fully_healthy(self):
        eng = GuardrailEngine()
        dash = eng.dashboard()
        assert dash["evidence_coverage_pct"] == 100.0
        assert dash["regulatory_source_validity_pct"] == 100.0
        assert dash["calculation_validation_pct"] == 100.0
        assert dash["human_review_required"] is False
        assert dash["approval_required"] is False


class TestAssessConfidenceIntegration:
    def test_confidence_reflects_a_logged_conflict(self):
        eng = GuardrailEngine()
        eng.check_tool_result("get_production_data", {"status": "conflict", "raw_records": []})
        assessment = eng.assess_confidence()
        assert assessment.level == "LOW"


class TestValidateOutputIntegration:
    def test_blocked_output_is_logged(self):
        eng = GuardrailEngine()
        result = eng.validate_output("Is the plant legally compliant?", "Yes, fully compliant.", human_review_required=False)
        assert result.passed is False
        assert any(e.guardrail == "OUTPUT_VALIDATION_FAILED" for e in eng.events)
