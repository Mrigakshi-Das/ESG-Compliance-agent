"""Phase 4 tests: the regulatory knowledge base itself -- schema integrity,
the source registry, the repository, staleness flagging, and applicability
logic. Distinct from test_tools_documents_regulations_evidence.py, which
tests the search_regulations *tool* wrapper.
"""

import pytest

from app.regulations import bee, environmental, sebi
from app.regulations.applicability import evaluate_condition, evaluate_requirement
from app.regulations.loader import load_source_registry
from app.regulations.repository import all_requirements, flag_outdated, get_by_id, search
from app.regulations.schema import ApplicabilityCondition

REQUIRED_FIELDS = [
    "requirement_id", "regulation", "authority", "industry", "requirement_description",
    "applicability", "metric", "unit", "target", "reporting_period", "reporting_frequency",
    "required_evidence", "effective_date", "source_id", "source_title", "source_url",
    "source_date", "last_reviewed", "confidence", "status", "version",
]


class TestKnowledgeBaseIntegrity:
    def test_all_four_scoped_regulations_present(self):
        regs = {r.regulation for r in all_requirements()}
        assert any("Perform, Achieve and Trade" in r for r in regs)
        assert any("Carbon Credit Trading Scheme" in r for r in regs)
        assert any(r == "Business Responsibility and Sustainability Reporting (BRSR)" for r in regs)
        assert any("BRSR Core" in r for r in regs)

    def test_environmental_module_empty_by_design(self):
        # Phase 4 brief: "do not attempt to cover every environmental regulation" --
        # environmental.py stays a placeholder for a later phase.
        assert environmental.load_requirements() == []

    def test_every_requirement_has_every_required_field(self):
        for r in all_requirements():
            for field in REQUIRED_FIELDS:
                assert getattr(r, field), f"{r.requirement_id} missing/empty {field}"

    def test_requirement_ids_are_unique(self):
        ids = [r.requirement_id for r in all_requirements()]
        assert len(ids) == len(set(ids))

    def test_every_requirement_cites_a_registered_source(self):
        registry_ids = {s["source_id"] for s in load_source_registry()}
        for r in all_requirements():
            assert r.source_id in registry_ids, f"{r.requirement_id} cites unregistered source {r.source_id}"

    def test_confidence_and_status_are_valid_values(self):
        for r in all_requirements():
            assert r.confidence in ("High", "Medium", "Low")
            assert r.status in ("Active", "Under Amendment", "Draft/Proposed", "Superseded")

    def test_bee_and_sebi_modules_return_the_expected_counts(self):
        assert len(bee.load_requirements()) == 6  # 3 PAT + 3 CCTS
        assert len(sebi.load_requirements()) == 4  # BRSR + 3 BRSR Core


class TestRepository:
    def test_get_by_id(self):
        r = get_by_id("SEBI-BRSRCORE-002")
        assert r is not None
        assert r.regulation == "BRSR Core -- Assurance/Assessment"

    def test_get_by_id_unknown_returns_none(self):
        assert get_by_id("NOT-A-REAL-ID") is None

    def test_search_matches_description_not_just_regulation_name(self):
        results = search("Designated Consumer")
        assert any(r.requirement_id.startswith("BEE-PAT") for r in results)

    def test_search_reporting_period_filter(self):
        results = search("BRSR Core", reporting_period="FY2023-24")
        assert results
        assert all("FY2023-24" in r.reporting_period for r in results)


class TestStaleness:
    def test_not_outdated_when_recently_reviewed(self):
        r = get_by_id("SEBI-BRSR-001")
        assert r.is_potentially_outdated("2026-09-12") is False  # reviewed same day

    def test_outdated_after_staleness_window(self):
        r = get_by_id("SEBI-BRSR-001")
        assert r.is_potentially_outdated("2028-01-01") is True  # ~16 months later

    def test_boundary_at_exactly_365_days_is_not_yet_outdated(self):
        r = get_by_id("SEBI-BRSR-001")  # last_reviewed 2026-09-12
        assert r.is_potentially_outdated("2027-09-12") is False  # exactly 365 days
        assert r.is_potentially_outdated("2027-09-13") is True  # 366 days

    def test_flag_outdated_over_the_whole_kb(self):
        # Every record was last_reviewed "2026-09-12" in this phase, so as of
        # that same date nothing should be flagged.
        assert flag_outdated(all_requirements(), "2026-09-12") == []


class TestApplicabilityLogic:
    def test_condition_applicable_when_fact_true(self):
        condition = ApplicabilityCondition("plant", "designated_consumer_status", "desc")
        verdict, reason = evaluate_condition(condition, {"designated_consumer_status": True})
        assert verdict == "Applicable"

    def test_condition_not_applicable_when_fact_false(self):
        condition = ApplicabilityCondition("plant", "obligated_entity_status", "desc")
        verdict, reason = evaluate_condition(condition, {"obligated_entity_status": False})
        assert verdict == "Not Applicable"

    def test_condition_cannot_determine_when_fact_missing(self):
        condition = ApplicabilityCondition("company", "listed_entity_market_cap_rank", "desc")
        verdict, reason = evaluate_condition(condition, {})
        assert verdict == "Cannot Determine"
        assert "No fact supplied" in reason

    def test_condition_rejects_non_boolean_fact(self):
        condition = ApplicabilityCondition("plant", "designated_consumer_status", "desc")
        verdict, reason = evaluate_condition(condition, {"designated_consumer_status": "yes"})
        assert verdict == "Cannot Determine"

    def test_requirement_applicable_when_all_conditions_satisfied(self):
        r = get_by_id("BEE-CCTS-003")  # its only condition references obligated_entity_status
        result = evaluate_requirement(r, {"obligated_entity_status": True})
        assert result["verdict"] == "Applicable"

    def test_requirement_not_applicable_when_any_condition_fails(self):
        r = get_by_id("BEE-CCTS-001")
        result = evaluate_requirement(r, {"obligated_entity_status": False})
        assert result["verdict"] == "Not Applicable"

    def test_requirement_cannot_determine_without_facts(self):
        r = get_by_id("BEE-PAT-001")
        result = evaluate_requirement(r, {})
        assert result["verdict"] == "Cannot Determine"
        assert len(result["reasons"]) == len(r.applicability_conditions)

    def test_real_kb_never_claims_a_fictional_plant_is_an_obligated_entity(self):
        # The Phase 2 demo plants (Plant A/B/C) are fictional and cannot
        # appear in the real GEI Target Rules Schedule -- with no fact
        # supplied, the honest verdict is "Cannot Determine", never "Applicable".
        r = get_by_id("BEE-CCTS-001")
        result = evaluate_requirement(r, known_facts={})
        assert result["verdict"] == "Cannot Determine"
