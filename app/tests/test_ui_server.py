"""Tests for app.ui.server -- the Flask API behind the control-tower
frontend. Uses Flask's test client (no real HTTP server needed); every
route is a thin wrapper over app.agent.orchestrator.run, so these tests
mostly confirm the JSON serialization is correct and complete.
"""

import json

import pytest

from app.ui.server import app as flask_app


@pytest.fixture()
def client():
    flask_app.config.update(TESTING=True)
    with flask_app.test_client() as c:
        yield c


class TestStaticPages:
    def test_index_serves_html(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert b"Cement ESG" in res.data

    def test_static_js_served(self, client):
        res = client.get("/app.js")
        assert res.status_code == 200

    def test_static_css_served(self, client):
        res = client.get("/styles.css")
        assert res.status_code == 200


class TestConfigEndpoint:
    def test_returns_plants_periods_types(self, client):
        res = client.get("/api/config")
        data = res.get_json()
        assert data["plants"] == ["Plant A", "Plant B", "Plant C"]
        assert data["default_period"] == data["periods"][-1]
        assert len(data["assessment_types"]) == 6
        assert len(data["example_queries"]) >= 1

    def test_every_assessment_type_has_a_working_template(self, client):
        data = client.get("/api/config").get_json()
        for t in data["assessment_types"]:
            filled = t["template"].format(plant="Plant A", period="FY2025-26 Q4")
            assert "{" not in filled


class TestRunEndpoint:
    def test_full_assessment_returns_readiness_score(self, client):
        res = client.post("/api/run", json={"query": "", "plant": "Plant B", "period": "FY2025-26 Q4", "assessment_type": "full_assessment"})
        data = res.get_json()
        assert res.status_code == 200
        assert data["readiness_score"]["overall_score"] > 0
        assert len(data["readiness_score"]["breakdown"]) == 4
        assert data["key_gaps"]
        assert data["priority_actions"]
        assert data["has_report"] is True

    def test_single_metric_query_has_no_dashboard_sections(self, client):
        res = client.post("/api/run", json={"query": "Calculate Plant A's emission intensity."})
        data = res.get_json()
        assert data["readiness_score"] is None
        assert data["key_gaps"] == []
        assert data["has_report"] is False
        assert "tCO2e" in data["final_answer"]

    def test_activity_trace_uses_only_the_three_symbols(self, client):
        res = client.post("/api/run", json={"query": "Calculate Plant A's emission intensity."})
        data = res.get_json()
        for entry in data["activity_trace"]:
            assert entry["symbol"] in ("✓", "⚠", "✗")

    def test_missing_data_scenario_returns_incomplete_status(self, client):
        # KNOWN_DATA_ISSUES.md #1: Plant C has no production for FY2025-26 Q3.
        res = client.post("/api/run", json={"query": "Calculate Plant C's emission intensity.", "period": "FY2025-26 Q3"})
        data = res.get_json()
        assert data["status"] == "incomplete_missing_data"
        assert "Unable to complete assessment" in data["final_answer"]
        assert data["confidence"] == "Low"
        assert data["human_review_required"] is True

    def test_root_cause_investigation_surfaces_hypothesis_findings(self, client):
        res = client.post("/api/run", json={"query": "Why did Plant B's carbon intensity increase?"})
        data = res.get_json()
        assert any(f["kind"] == "Hypothesis" for f in data["findings"])
        assert "Kiln Refractory Lining" in data["final_answer"]

    def test_compare_plants_query(self, client):
        res = client.post("/api/run", json={"query": "Compare plants on emission intensity for FY2025-26 Q4."})
        data = res.get_json()
        assert "Plant A" in data["final_answer"]

    def test_empty_body_falls_back_to_default_template(self, client):
        res = client.post("/api/run", json={})
        assert res.status_code == 200
        data = res.get_json()
        assert data["objective"]["intent"] == "full_assessment"

    def test_explicit_plant_hint_is_honored(self, client):
        res = client.post("/api/run", json={"query": "What is the water intensity?", "plant": "Plant C"})
        data = res.get_json()
        assert data["objective"]["plant"] == "Plant C"

    def test_query_text_plant_is_not_overridden_by_omitted_hint(self, client):
        # Mirrors the frontend fix: a typed query naming its own plant must
        # win when no hint is sent (server.py itself passes hints through
        # unmodified -- this just confirms the pass-through is correct).
        res = client.post("/api/run", json={"query": "What is Plant C's water intensity?", "plant": None, "period": None})
        data = res.get_json()
        assert data["objective"]["plant"] == "Plant C"

    def test_response_is_json_serializable_end_to_end(self, client):
        res = client.post("/api/run", json={"query": "", "plant": "Plant B", "period": "FY2025-26 Q4", "assessment_type": "full_assessment"})
        # get_data + json.loads exercises the exact bytes Flask sent, not
        # just the parsed dict test client conveniently reconstructs.
        json.loads(res.get_data(as_text=True))


class TestReportPdfEndpoint:
    def test_returns_valid_pdf(self, client):
        res = client.get("/api/report.pdf?plant=Plant%20A&period=FY2025-26%20Q4")
        assert res.status_code == 200
        assert res.mimetype == "application/pdf"
        assert res.data[:5] == b"%PDF-"

    def test_content_disposition_names_plant_and_period(self, client):
        res = client.get("/api/report.pdf?plant=Plant%20B&period=FY2025-26%20Q4")
        assert "Plant_B" in res.headers["Content-Disposition"]

    def test_unknown_plant_rejected(self, client):
        res = client.get("/api/report.pdf?plant=Plant%20Z&period=FY2025-26%20Q4")
        assert res.status_code == 400

    def test_unknown_period_rejected(self, client):
        res = client.get("/api/report.pdf?plant=Plant%20A&period=not-a-period")
        assert res.status_code == 400

    def test_missing_params_use_defaults(self, client):
        res = client.get("/api/report.pdf")
        assert res.status_code == 200
