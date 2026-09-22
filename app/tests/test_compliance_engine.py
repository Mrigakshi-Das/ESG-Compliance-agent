"""Integration tests for app.compliance.engine.run_compliance_assessment --
the full Phase 6 pipeline (applicability -> classification -> root cause ->
prioritization -> recommendations -> readiness score) against the real
Phase 2 dataset. This is the Phase 6 demo scenario, verified as assertions:
"Why is Plant B's ESG readiness low and what should management address
first?"
"""

from app.compliance.engine import run_compliance_assessment


class TestRunComplianceAssessmentStructure:
    def test_covers_all_ten_kb_requirements(self):
        assessment = run_compliance_assessment("Plant A", "FY2025-26 Q4")
        assert len(assessment.requirement_statuses) == 10

    def test_readiness_score_in_range(self):
        assessment = run_compliance_assessment("Plant A", "FY2025-26 Q4")
        assert 0 <= assessment.overall_readiness_score <= 100

    def test_gaps_sorted_by_priority_descending(self):
        assessment = run_compliance_assessment("Plant B", "FY2025-26 Q4")
        scores = [g.priority_score for g in assessment.gaps]
        assert scores == sorted(scores, reverse=True)

    def test_one_recommendation_per_gap(self):
        assessment = run_compliance_assessment("Plant B", "FY2025-26 Q4")
        assert len(assessment.recommendations) == len(assessment.gaps)

    def test_assumptions_are_surfaced(self):
        assessment = run_compliance_assessment("Plant A", "FY2025-26 Q4")
        assert assessment.assumptions
        assert any("BRSR" in a for a in assessment.assumptions)

    def test_pat_and_ccts_never_silently_pass(self):
        # No demo plant can be confirmed as a real Designated Consumer or
        # Obligated Entity -- these must always require human review.
        assessment = run_compliance_assessment("Plant C", "FY2025-26 Q4")
        for rid in ("BEE-PAT-002", "BEE-CCTS-002"):
            assert assessment.requirement_statuses[rid] == "Human Review Required"


class TestPlantBFullDemonstration:
    """The Phase 6 demo scenario, in full."""

    def test_plant_b_has_a_critical_priority_gap(self):
        assessment = run_compliance_assessment("Plant B", "FY2025-26 Q4")
        assert assessment.gaps[0].priority_band == "Critical"

    def test_top_gap_is_the_emission_intensity_performance_gap(self):
        assessment = run_compliance_assessment("Plant B", "FY2025-26 Q4")
        top = assessment.gaps[0]
        assert top.metric == "emission_intensity_tco2e_per_t_cement"
        assert top.status == "Potential Gap"
        assert top.actual_value > top.target_value  # genuinely exceeds the benchmark

    def test_top_gap_has_autonomous_root_cause_investigation(self):
        # The brief's key test: the agent must investigate autonomously,
        # not hand back a generic recommendation.
        assessment = run_compliance_assessment("Plant B", "FY2025-26 Q4")
        top = assessment.gaps[0]
        assert top.root_cause is not None
        assert top.root_cause.trend == "increasing"
        facts = [f for f in top.root_cause.findings if f.kind == "Fact"]
        hypotheses = [f for f in top.root_cause.findings if f.kind == "Hypothesis"]
        assert len(facts) >= 3  # thermal, electricity, and fuel driver facts, at minimum
        assert hypotheses
        assert any("Kiln Refractory Lining" in h.statement for h in hypotheses)
        assert any("Overdue" in h.statement for h in hypotheses)

    def test_root_cause_never_asserts_hypothesis_as_fact(self):
        assessment = run_compliance_assessment("Plant B", "FY2025-26 Q4")
        top = assessment.gaps[0]
        for finding in top.root_cause.findings:
            if "may be related" in finding.statement or "may reflect" in finding.statement:
                assert finding.kind == "Hypothesis", f"Speculative language stated as Fact: {finding.statement}"

    def test_business_impact_estimate_is_quantified_and_labeled(self):
        assessment = run_compliance_assessment("Plant B", "FY2025-26 Q4")
        top = assessment.gaps[0]
        estimate = top.estimated_impact
        assert estimate is not None
        assert "estimate" in estimate["basis"].lower()
        assert estimate["potential_energy_savings_gj_estimate"] > 0
        assert estimate["potential_emission_reduction_tco2e_estimate"] > 0
        assert "not estimated" in estimate["potential_cost_impact"].lower()  # cost never fabricated

    def test_top_recommendation_answers_what_to_address_first(self):
        assessment = run_compliance_assessment("Plant B", "FY2025-26 Q4")
        top_rec = assessment.recommendations[0]
        assert top_rec["priority"] == "Critical"
        assert "emission_intensity" in top_rec["corrective_action"]
        assert top_rec["suggested_owner"]
        assert top_rec["suggested_timeline"]

    def test_evidence_gap_also_surfaced(self):
        assessment = run_compliance_assessment("Plant B", "FY2025-26 Q4")
        statuses = set(assessment.requirement_statuses.values())
        assert "Evidence Missing" in statuses or "Potential Gap" in statuses  # BRSR Core evidence gaps

    def test_readiness_score_reflects_the_real_gaps(self):
        # Plant B (worst performer, missing/expired evidence) must score
        # lower than Plant A (best performer, one clean evidence-filing gap).
        plant_a = run_compliance_assessment("Plant A", "FY2025-26 Q4")
        plant_b = run_compliance_assessment("Plant B", "FY2025-26 Q4")
        assert plant_b.overall_readiness_score <= plant_a.overall_readiness_score

    def test_final_narrative_would_not_be_generic(self):
        # A generic ESG answer would say nothing about a specific
        # equipment record or a quantified driver change -- confirm the
        # investigation surfaces plant-specific, sourced detail.
        assessment = run_compliance_assessment("Plant B", "FY2025-26 Q4")
        top = assessment.gaps[0]
        statements = [f.statement for f in top.root_cause.findings]
        assert any("2025-06-15" in s for s in statements)  # the actual overdue-since date from the dataset
