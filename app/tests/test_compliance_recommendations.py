"""Unit tests for app.compliance.recommendations: the corrective-action
engine. Verifies every recommendation carries all 9 required fields, and
that business-impact estimates are clearly labeled and never fabricated
when no cost data exists.
"""

from app.compliance.gap_analysis import RootCauseFinding, RootCauseInvestigation
from app.compliance.prioritization import prioritize_gaps
from app.compliance.recommendations import build_recommendation
from app.compliance.types import Gap

_REQUIRED_FIELDS = {
    "gap", "evidence", "root_cause", "corrective_action", "suggested_owner",
    "suggested_timeline", "esg_impact", "business_impact", "closure_evidence",
}


def _prioritized_gap(**kwargs) -> Gap:
    gap = Gap(plant="Plant B", period="FY2025-26 Q4", requirement_id="TEST-1", regulation="Test Regulation", **kwargs)
    return prioritize_gaps([gap])[0]


class TestBuildRecommendation:
    def test_all_required_fields_present(self):
        rec = build_recommendation(_prioritized_gap(status="Evidence Missing", missing_evidence=["BRSR Annual Report"]))
        assert _REQUIRED_FIELDS.issubset(rec.keys())
        assert all(rec[f] for f in _REQUIRED_FIELDS)

    def test_evidence_missing_recommendation_names_the_document(self):
        rec = build_recommendation(_prioritized_gap(status="Evidence Missing", missing_evidence=["BRSR Annual Report"]))
        assert "BRSR Annual Report" in rec["corrective_action"]
        assert "BRSR Annual Report" in rec["evidence"]

    def test_root_cause_not_investigated_is_stated_plainly(self):
        rec = build_recommendation(_prioritized_gap(status="Evidence Missing"))
        assert "not investigated" in rec["root_cause"].lower()

    def test_root_cause_phrased_as_hypothesis_never_fact(self):
        investigation = RootCauseInvestigation(
            plant="Plant B", metric="emission_intensity_tco2e_per_t_cement", trend="increasing",
            findings=[
                RootCauseFinding("Fact", "Thermal energy consumption increased 12%.", "High"),
                RootCauseFinding("Hypothesis", "The increase may be related to kiln efficiency deterioration.", "Medium"),
            ],
            contributing_factors=["Overdue maintenance: Kiln"],
        )
        gap = _prioritized_gap(status="Potential Gap", metric="emission_intensity_tco2e_per_t_cement", variance_pct=15.0)
        gap.root_cause = investigation
        rec = build_recommendation(gap)
        assert rec["root_cause"].startswith("Hypothesis:")
        assert "may be related" in rec["root_cause"]
        assert "Thermal energy consumption increased 12%" not in rec["root_cause"]  # facts stay out of the root-cause field

    def test_estimate_is_used_when_present_and_labeled(self):
        gap = _prioritized_gap(status="Potential Gap", metric="emission_intensity_tco2e_per_t_cement", variance_pct=15.0)
        gap.estimated_impact = {
            "basis": "Estimate: illustrative, based on historical variation.",
            "potential_energy_savings_gj_estimate": 1000.0,
            "potential_cost_impact": "Not estimated -- no energy/fuel cost data is configured in this system.",
        }
        rec = build_recommendation(gap)
        assert rec["business_impact"]["estimates"]["potential_energy_savings_gj_estimate"] == 1000.0
        assert "estimate" in rec["business_impact"]["estimates"]["basis"].lower()
        assert "not estimated" in rec["business_impact"]["estimates"]["potential_cost_impact"].lower()

    def test_no_estimate_is_stated_plainly_not_fabricated(self):
        rec = build_recommendation(_prioritized_gap(status="Data Missing"))
        assert "no quantified estimate" in rec["business_impact"]["estimates"]["note"].lower()

    def test_priority_is_carried_through(self):
        rec = build_recommendation(_prioritized_gap(status="Data Conflict"))
        assert rec["priority"] in ("Critical", "High", "Medium", "Low")
        assert isinstance(rec["priority_score"], float)

    def test_owner_and_timeline_vary_by_status(self):
        evidence_rec = build_recommendation(_prioritized_gap(status="Evidence Missing"))
        human_review_rec = build_recommendation(_prioritized_gap(status="Human Review Required"))
        assert evidence_rec["suggested_owner"] != human_review_rec["suggested_owner"]
