"""End-to-end tests for app.agent.orchestrator.run against the real Phase 2
dataset -- these are the "5+ autonomous demonstrations" exercised as
assertions rather than printed output, plus the stopping-condition and
error-handling tests the Phase 5 brief calls for.
"""

from app.agent.orchestrator import MISSING_DATA_MESSAGE, render_activity_trace, run


class TestExampleScenarios:
    """The three worked examples from the Phase 5 brief, verified exactly."""

    def test_example_1_single_metric_calculation(self):
        state = run("Calculate Plant A's emission intensity.")
        assert state.tools_called == ["get_emission_data", "get_production_data", "calculate_emission_intensity"]
        assert "get_water_data" not in state.tools_called
        assert "get_waste_data" not in state.tools_called
        assert "get_maintenance_data" not in state.tools_called
        assert "search_documents" not in state.tools_called
        assert state.final_answer is not None
        assert "tCO2e per tonne cement" in state.final_answer
        assert state.status == "completed"

    def test_example_2_full_assessment_uses_broad_tool_set(self):
        # Phase 6: full_assessment now delegates to the compliance engine
        # (app.compliance.engine.run_compliance_assessment), which
        # internally calls production/emissions/energy/documents/evidence
        # tools for every applicable requirement -- broader and more
        # rigorous than a flat tool list can express. The full internal
        # detail is preserved on the returned ComplianceAssessment.
        state = run("Assess Plant A's ESG compliance readiness.")
        assert state.tools_called == ["run_compliance_assessment", "generate_compliance_report"]
        assessment = state.tool_results["run_compliance_assessment"]
        assert assessment.plant == "Plant A"
        assert len(assessment.requirement_statuses) == 10  # all 10 Phase 4 KB requirements considered
        assert 0 <= assessment.overall_readiness_score <= 100
        # Phase 7: the report's category-weighted score is "the" headline
        # number now, distinct from Phase 6's flat KB-status average.
        assert state.report is not None
        assert state.calculations["overall_readiness_score"] == state.report.readiness_score["overall_score"]
        assert state.calculations["kb_status_readiness_score"] == assessment.overall_readiness_score

    def test_example_3_root_cause_investigation(self):
        # Phase 6: delegates to app.compliance.gap_analysis.investigate_root_cause.
        state = run("Why did Plant B's carbon intensity increase?")
        assert state.tools_called == ["investigate_root_cause"]
        assert any(f.kind == "Hypothesis" for f in state.findings)
        # The hypothesis must be traceable to a real overdue maintenance
        # record (KNOWN_DATA_ISSUES.md #9), not an invented cause.
        assert "Kiln Refractory Lining" in state.final_answer
        investigation = state.tool_results["investigate_root_cause"]
        assert investigation.trend == "increasing"
        assert any("Kiln Refractory Lining" in f.statement for f in investigation.findings if f.kind == "Hypothesis")


class TestAdditionalDemonstrations:
    """Objectives beyond the three worked examples, to show the tool
    sequence is a genuine function of the input, not a lookup of three
    pre-baked answers."""

    def test_cross_plant_comparison(self):
        state = run("Compare plants on emission intensity for FY2025-26 Q4.")
        assert state.tools_called == ["compare_plants"]
        assert state.tool_results["compare_plants"]["ranked"] == ["Plant A", "Plant C", "Plant B"]

    def test_regulatory_lookup_touches_no_plant_data(self):
        state = run("What does BRSR Core require?")
        assert state.tools_called == ["search_regulations"]
        assert not any(t.startswith("get_") for t in state.tools_called)

    def test_evidence_audit(self):
        state = run("Audit Plant B's evidence readiness.")
        assert "search_documents" in state.tools_called
        assert "assess_evidence" in state.tools_called
        assert "get_production_data" not in state.tools_called  # no calc needed for a pure evidence audit
        assert state.human_review_required is True

    def test_evidence_audit_uses_matchable_short_labels_not_raw_kb_text(self):
        # Regression test: _execute_evidence_audit used to pass assess_evidence
        # the KB's long, human-readable required_evidence citations (e.g. "GHG
        # Verification Statement / accredited carbon verification agency
        # report"), which can never substring-match a document's short
        # document_type value, so EVERY audit reported "Missing" across the
        # board regardless of what was actually on file. Plant B genuinely
        # has a valid "GHG Verification Statement" and "BRSR Annual Report"
        # on file (app/data/seed_csv/evidence.csv), so a correct audit must
        # find real matches -- not report blanket Missing.
        state = run("Audit Plant B's evidence readiness.")
        result = state.tool_results["assess_evidence"]
        assert result["evidence_status"] != "Missing"
        assert result["matched_evidence"]  # at least one required type actually matched a document
        assert not any(" / " in m for m in result["missing_evidence"])  # never a raw KB citation

    def test_generic_single_domain_lookup(self):
        state = run("How much waste did Plant A generate?")
        assert state.tools_called == ["get_waste_data"]

    def test_thermal_energy_query_reports_thermal_not_electrical(self):
        # Regression test: planner.py's _ENERGY_WORDS routes "thermal"/
        # "specific energy" wording to the single_metric_energy intent
        # alongside plain "energy intensity" wording, but the handler used
        # to always compute and report electrical energy intensity
        # regardless of which one was actually asked about.
        state = run("What is Plant B's specific thermal energy consumption?")
        assert state.tools_called == ["get_energy_data"]
        assert "GJ per tonne clinker" in state.final_answer
        assert "electrical" not in state.final_answer.lower()

    def test_electricity_query_reports_electricity_not_intensity(self):
        state = run("What is Plant B's electricity consumption?")
        assert state.tools_called == ["get_energy_data"]
        assert "MWh" in state.final_answer

    def test_generic_energy_query_still_reports_electrical_intensity(self):
        state = run("What is Plant A's energy intensity?")
        assert state.tools_called == ["get_energy_data", "get_production_data", "calculate_energy_intensity"]
        assert "kWh per tonne cement" in state.final_answer

    def test_novel_multi_domain_question_not_in_any_worked_example(self):
        state = run("Show me Plant C's water and waste figures.")
        assert set(state.tools_called) == {"get_water_data", "get_waste_data"}


class TestStoppingConditions:
    def test_missing_production_data_returns_exact_required_message(self):
        # KNOWN_DATA_ISSUES.md #1: Plant C has no production row for FY2025-26 Q3.
        state = run("Calculate Plant C's emission intensity.", period_hint="FY2025-26 Q3")
        assert state.final_answer == MISSING_DATA_MESSAGE
        assert state.status == "incomplete_missing_data"
        assert state.confidence == "Low"
        assert state.human_review_required is True
        # get_emission_data still ran and returned real data -- the agent
        # must not fabricate the missing production figure to proceed anyway.
        assert state.tool_results["get_emission_data"]["status"] == "ok"
        assert state.tool_results["get_production_data"]["status"] == "missing"

    def test_conflicting_production_data_is_not_averaged_or_guessed(self):
        # KNOWN_DATA_ISSUES.md #2: Plant C has two conflicting production
        # rows for FY2025-26 Q2.
        state = run("What is Plant C's emission intensity?", period_hint="FY2025-26 Q2")
        assert state.final_answer == MISSING_DATA_MESSAGE
        assert state.tool_results["get_production_data"]["status"] == "conflict"
        assert any("conflicting production records" in f for f in state.data_quality_flags)

    def test_does_not_call_tools_indefinitely(self):
        # A bounded number of tool calls for a bounded intent -- the
        # rule-based planner never loops.
        state = run("Assess Plant A's ESG compliance readiness.")
        assert len(state.tools_called) < 20


class TestDecisionTrace:
    def test_trace_never_exposes_raw_reasoning(self):
        state = run("Calculate Plant A's emission intensity.")
        trace = render_activity_trace(state)
        assert len(trace) >= 3
        for entry in trace:
            assert entry["symbol"] in ("✓", "⚠", "✗")
            assert isinstance(entry["description"], str)

    def test_trace_shows_objective_plan_and_decision(self):
        state = run("Calculate Plant A's emission intensity.")
        descriptions = [e["description"] for e in render_activity_trace(state)]
        assert any("Objective identified" in d for d in descriptions)
        assert any("Plan created" in d for d in descriptions)
        assert any("Decision:" in d for d in descriptions)

    def test_human_review_warning_appears_in_trace_when_flagged(self):
        state = run("Audit Plant B's evidence readiness.")
        descriptions = [e["description"] for e in render_activity_trace(state)]
        assert any("Human review required" in d for d in descriptions)


class TestAgentState:
    def test_assumptions_are_recorded_as_findings(self):
        state = run("Calculate Plant A's emission intensity.")
        assumption_findings = [f for f in state.findings if f.kind == "Assumption"]
        assert any("no reporting period" in f.statement.lower() for f in assumption_findings)

    def test_findings_are_labeled_fact_vs_calculation(self):
        state = run("Calculate Plant A's emission intensity.")
        kinds = {f.kind for f in state.findings}
        assert "Fact" in kinds
        assert "Calculation" in kinds

    def test_requirements_reflect_the_selected_tools(self):
        state = run("Calculate Plant A's emission intensity.")
        assert state.requirements == ["get_emission_data", "get_production_data", "calculate_emission_intensity"]

    def test_state_carries_objective_plan_and_confidence(self):
        state = run("Calculate Plant A's emission intensity.")
        assert state.objective is not None
        assert state.plan
        assert state.confidence in ("High", "Medium", "Low")
