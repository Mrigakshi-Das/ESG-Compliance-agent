"""Unit tests for app.compliance.requirements: applicability resolution
using the Phase 4 knowledge base + evaluator and the documented demo
assumptions in app.compliance.context.
"""

from app.compliance.requirements import get_applicable_requirements


class TestGetApplicableRequirements:
    def test_returns_all_ten_kb_requirements(self):
        results = get_applicable_requirements("Plant B")
        assert len(results) == 10

    def test_pat_and_ccts_are_cannot_determine(self):
        # No real gazette DC/obligated-entity registry exists in this
        # prototype -- these must never resolve "Applicable" by guessing.
        results = {r.requirement.requirement_id: r for r in get_applicable_requirements("Plant B")}
        for rid in ("BEE-PAT-001", "BEE-PAT-002", "BEE-PAT-003", "BEE-CCTS-001", "BEE-CCTS-002", "BEE-CCTS-003"):
            assert results[rid].applicability_verdict == "Cannot Determine"

    def test_brsr_is_applicable_under_the_documented_assumption(self):
        results = {r.requirement.requirement_id: r for r in get_applicable_requirements("Plant B")}
        assert results["SEBI-BRSR-001"].applicability_verdict == "Applicable"
        assert results["SEBI-BRSRCORE-001"].applicability_verdict == "Applicable"
        assert results["SEBI-BRSRCORE-002"].applicability_verdict == "Applicable"

    def test_brsr_core_value_chain_is_unresolvable(self):
        # value_chain_partner_share has no fact in DEMO_KNOWN_FACTS -- this
        # must stay Cannot Determine even though the market-cap fact is assumed.
        results = {r.requirement.requirement_id: r for r in get_applicable_requirements("Plant B")}
        assert results["SEBI-BRSRCORE-003"].applicability_verdict == "Cannot Determine"

    def test_reasons_are_non_empty_for_every_requirement(self):
        for item in get_applicable_requirements("Plant A"):
            assert item.applicability_reasons

    def test_same_result_for_every_plant(self):
        # The demo assumption is applied uniformly, not per-plant.
        a = [r.applicability_verdict for r in get_applicable_requirements("Plant A")]
        b = [r.applicability_verdict for r in get_applicable_requirements("Plant B")]
        c = [r.applicability_verdict for r in get_applicable_requirements("Plant C")]
        assert a == b == c
