"""Unit tests for app.agent.planner: objective parsing and dynamic intent
classification / tool selection. No tools are actually called here -- see
test_agent_orchestrator.py for end-to-end runs.
"""

from app.agent.planner import build_plan, infer_metric_key, parse_objective, plan_tasks, select_tools
from app.data.constants import PERIODS, PLANTS


class TestParseObjective:
    def test_extracts_plant_and_period(self):
        obj = parse_objective("Calculate Plant B's emission intensity for FY2025-26 Q2.")
        assert obj.plant == "Plant B"
        assert obj.reporting_period == "FY2025-26 Q2"
        assert obj.assumptions == []

    def test_defaults_missing_plant_with_assumption(self):
        obj = parse_objective("What is the emission intensity?")
        assert obj.plant == PLANTS[0]
        assert any("no plant named" in a.lower() for a in obj.assumptions)

    def test_defaults_missing_period_with_assumption(self):
        obj = parse_objective("Calculate Plant A's emission intensity.")
        assert obj.reporting_period == PERIODS[-1]
        assert any("no reporting period" in a.lower() for a in obj.assumptions)

    def test_explicit_hints_override_text_extraction(self):
        obj = parse_objective("Calculate emission intensity.", plant_hint="Plant C", period_hint="FY2024-25 Q3")
        assert obj.plant == "Plant C"
        assert obj.reporting_period == "FY2024-25 Q3"

    def test_comparison_intent_does_not_default_a_single_plant(self):
        obj = parse_objective("Compare plants on emission intensity.")
        assert obj.intent == "cross_plant_comparison"
        assert obj.plant is None

    def test_mentions_multiple_plants_in_order(self):
        obj = parse_objective("Compare Plant B and Plant A on energy intensity.")
        assert obj.mentioned_plants == ["Plant B", "Plant A"]

    def test_priority_word_captured(self):
        obj = parse_objective("Urgent: assess Plant A's ESG readiness.")
        assert obj.stated_priority == "urgent"

    def test_no_priority_word_is_none(self):
        obj = parse_objective("Calculate Plant A's emission intensity.")
        assert obj.stated_priority is None


class TestIntentClassification:
    def test_single_metric_emission(self):
        assert parse_objective("Calculate Plant A's emission intensity.").intent == "single_metric_emission"

    def test_single_metric_energy(self):
        assert parse_objective("What is Plant B's energy intensity?").intent == "single_metric_energy"

    def test_single_metric_water(self):
        assert parse_objective("What is Plant C's water intensity?").intent == "single_metric_water"

    def test_single_metric_waste(self):
        assert parse_objective("How much waste did Plant A generate?").intent == "single_metric_waste"

    def test_full_assessment(self):
        assert parse_objective("Assess Plant A's ESG compliance readiness.").intent == "full_assessment"

    def test_root_cause_investigation(self):
        assert parse_objective("Why did Plant B's carbon intensity increase?").intent == "root_cause_investigation"

    def test_root_cause_requires_both_why_and_trend_word(self):
        # "why" alone, with no trend word, should not force a historical
        # investigation -- it should fall through to a narrower intent.
        obj = parse_objective("Why is Plant A's emission intensity 0.57?")
        assert obj.intent != "root_cause_investigation"

    def test_cross_plant_comparison(self):
        assert parse_objective("Which plant performs best on emission intensity?").intent == "cross_plant_comparison"

    def test_evidence_audit_takes_priority_over_generic_readiness(self):
        assert parse_objective("Audit Plant B's evidence readiness.").intent == "evidence_audit"

    def test_regulatory_lookup_with_no_plant_named(self):
        assert parse_objective("What does BRSR Core require?").intent == "regulatory_lookup"

    def test_generic_data_lookup_for_multi_domain_question(self):
        # emission + energy both mentioned, no calc/assessment verbs -- an
        # ambiguous multi-domain question falls back to a plain data lookup.
        obj = parse_objective("Show me Plant A's emission and energy figures.")
        assert obj.intent == "generic_data_lookup"


class TestBuildPlanAndToolSelection:
    def test_single_metric_emission_tool_sequence_matches_example_1(self):
        obj = parse_objective("Calculate Plant A's emission intensity.")
        tools = select_tools(obj)
        assert tools == ["get_emission_data", "get_production_data", "calculate_emission_intensity"]
        assert "get_water_data" not in tools
        assert "get_waste_data" not in tools
        assert "get_maintenance_data" not in tools
        assert "search_regulations" not in tools

    def test_full_assessment_tool_sequence_is_broad(self):
        obj = parse_objective("Assess Plant A's ESG compliance readiness.")
        tools = select_tools(obj)
        for expected in (
            "search_regulations", "get_production_data", "get_emission_data", "get_energy_data",
            "search_documents", "calculate_emission_intensity", "calculate_energy_intensity",
            "assess_evidence", "compare_with_target",
        ):
            assert expected in tools

    def test_root_cause_tool_sequence(self):
        # Phase 6: root-cause investigation delegates to the compliance
        # engine's investigate_root_cause, which internally walks
        # get_historical_metric across the full driver chain plus
        # get_maintenance_data -- declared here as one logical operation.
        obj = parse_objective("Why did Plant B's carbon intensity increase?")
        tools = select_tools(obj)
        assert tools == ["investigate_root_cause"]

    def test_different_objectives_yield_different_plans(self):
        # The core "do not hard-code one workflow" requirement: two
        # different objectives must not collapse to the same tool list.
        plan_1 = select_tools(parse_objective("Calculate Plant A's emission intensity."))
        plan_2 = select_tools(parse_objective("Assess Plant A's ESG compliance readiness."))
        plan_3 = select_tools(parse_objective("Why did Plant B's carbon intensity increase?"))
        plan_4 = select_tools(parse_objective("Compare plants on emission intensity."))
        assert len({tuple(plan_1), tuple(plan_2), tuple(plan_3), tuple(plan_4)}) == 4

    def test_plan_tasks_returns_human_readable_steps(self):
        steps = plan_tasks(parse_objective("Assess Plant A's ESG compliance readiness."))
        assert len(steps) >= 3
        assert all(isinstance(s, str) for s in steps)

    def test_build_plan_is_single_source_of_truth(self):
        obj = parse_objective("Calculate Plant A's emission intensity.")
        spec = build_plan(obj)
        assert plan_tasks(obj) == spec.steps
        assert select_tools(obj) == spec.tool_names


class TestInferMetricKey:
    def test_carbon_intensity_maps_to_emission_intensity(self):
        assert infer_metric_key("Why did carbon intensity increase?") == "emission_intensity_tco2e_per_t_cement"

    def test_scope_1_maps_correctly(self):
        assert infer_metric_key("scope 1 emissions trend") == "scope_1_tco2e"

    def test_thermal_energy_maps_correctly(self):
        assert infer_metric_key("thermal energy consumption") == "specific_thermal_energy_consumption_gj_per_t_clinker"

    def test_unrecognized_text_falls_back_to_default(self):
        assert infer_metric_key("something unrelated entirely") == "emission_intensity_tco2e_per_t_cement"
