"""Unit tests for app.compliance.gap_analysis: status classification and
root-cause investigation.
"""

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.compliance.gap_analysis import classify_requirement_status, investigate_root_cause


class TestClassifyRequirementStatus:
    def test_not_applicable_wins_immediately(self):
        status = classify_requirement_status("Not Applicable", "conflict", {"status": "Exceeds Target"}, "Missing")
        assert status == "Not Applicable"

    def test_cannot_determine_becomes_human_review_required(self):
        status = classify_requirement_status("Cannot Determine", "ok", None, "Compliant")
        assert status == "Human Review Required"

    def test_metric_conflict_wins_over_evidence(self):
        status = classify_requirement_status("Applicable", "conflict", None, "Missing")
        assert status == "Data Conflict"

    def test_metric_missing(self):
        status = classify_requirement_status("Applicable", "missing", None, None)
        assert status == "Data Missing"

    def test_fully_compliant(self):
        status = classify_requirement_status("Applicable", "ok", {"status": "Within Target"}, "Compliant")
        assert status == "Compliant"

    def test_no_metric_no_evidence_problem_is_compliant(self):
        status = classify_requirement_status("Applicable", None, None, "Compliant")
        assert status == "Compliant"

    def test_evidence_missing_when_target_is_fine(self):
        status = classify_requirement_status("Applicable", "ok", {"status": "Within Target"}, "Missing")
        assert status == "Evidence Missing"

    def test_evidence_outdated(self):
        status = classify_requirement_status("Applicable", "ok", {"status": "Within Target"}, "Outdated")
        assert status == "Evidence Outdated"

    def test_evidence_conflicting_maps_to_data_conflict(self):
        status = classify_requirement_status("Applicable", "ok", {"status": "Within Target"}, "Conflicting")
        assert status == "Data Conflict"

    def test_evidence_mixed_maps_to_potential_gap(self):
        status = classify_requirement_status("Applicable", "ok", {"status": "Within Target"}, "Mixed")
        assert status == "Potential Gap"

    def test_numeric_exceeds_target_is_potential_gap(self):
        status = classify_requirement_status("Applicable", "ok", {"status": "Exceeds Target"}, "Compliant")
        assert status == "Potential Gap"

    def test_evidence_missing_takes_priority_over_potential_gap(self):
        # Can't confirm the number is even real evidence-wise -- the more
        # fundamental problem (severity order) wins.
        status = classify_requirement_status("Applicable", "ok", {"status": "Exceeds Target"}, "Missing")
        assert status == "Evidence Missing"

    def test_never_returns_a_binary_non_compliant(self):
        # The 8-status vocabulary has no "Non-Compliant" -- every outcome
        # must be one of the defined statuses, and a numeric miss must
        # never be forced into a hard binary verdict.
        allowed = {
            "Compliant", "Potential Gap", "Data Missing", "Evidence Missing",
            "Evidence Outdated", "Data Conflict", "Not Applicable", "Human Review Required",
        }
        status = classify_requirement_status("Applicable", "ok", {"status": "Exceeds Target"}, None)
        assert status in allowed
        assert status == "Potential Gap"


class TestInvestigateRootCause:
    def test_plant_b_thermal_energy_increase_finds_kiln_hypothesis(self):
        investigation = investigate_root_cause("Plant B", "specific_thermal_energy_consumption_gj_per_t_clinker")
        assert investigation.trend == "increasing"
        facts = [f for f in investigation.findings if f.kind == "Fact"]
        hypotheses = [f for f in investigation.findings if f.kind == "Hypothesis"]
        assert facts  # real numeric facts were recorded
        assert any("Kiln Refractory Lining" in h.statement for h in hypotheses)
        assert "Kiln Refractory Lining" in investigation.contributing_factors[0] or any(
            "Kiln Refractory Lining" in c for c in investigation.contributing_factors
        )

    def test_never_states_hypothesis_as_fact(self):
        investigation = investigate_root_cause("Plant B", "emission_intensity_tco2e_per_t_cement")
        for finding in investigation.findings:
            if "may be related" in finding.statement or "may reflect" in finding.statement:
                assert finding.kind == "Hypothesis"

    def test_facts_are_quantified_not_vague(self):
        investigation = investigate_root_cause("Plant B", "specific_thermal_energy_consumption_gj_per_t_clinker")
        top_fact = next(f for f in investigation.findings if f.kind == "Fact")
        assert "%" in top_fact.statement

    def test_flat_or_decreasing_trend_skips_investigation(self):
        # Plant A's thermal SEC steadily improves (decreasing) -- no
        # investigation should be warranted.
        investigation = investigate_root_cause("Plant A", "specific_thermal_energy_consumption_gj_per_t_clinker")
        assert investigation.trend == "decreasing"
        assert investigation.contributing_factors == []
        assert len(investigation.findings) == 1
        assert investigation.findings[0].kind == "Fact"


class TestExternalFactorScan:
    """The broader, still-deterministic scan beyond the original
    production/electricity/thermal/fuel/maintenance chain -- fuel quality
    and weather, added so root-cause investigation has real, grounded
    hypothesis candidates outside that original fixed chain. Works with no
    ANTHROPIC_API_KEY; this is the no-key path."""

    def test_finds_the_fuel_quality_decline_for_plant_b(self):
        investigation = investigate_root_cause("Plant B", "specific_thermal_energy_consumption_gj_per_t_clinker")
        hypotheses = [f.statement for f in investigation.findings if f.kind == "Hypothesis"]
        assert any("calorific value" in h for h in hypotheses)
        assert any("ash content" in h for h in hypotheses)
        assert any(
            "External factor: gross_calorific_value_kcal_per_kg decreased" in c
            for c in investigation.contributing_factors
        )

    def test_facts_behind_the_new_hypotheses_are_quantified(self):
        investigation = investigate_root_cause("Plant B", "specific_thermal_energy_consumption_gj_per_t_clinker")
        facts = [f.statement for f in investigation.findings if f.kind == "Fact"]
        assert any("gross_calorific_value_kcal_per_kg decreased" in f and "%" in f for f in facts)

    def test_never_flags_a_factor_that_moved_the_helpful_direction(self):
        # Plant B's rainfall/humidity happen to fall (not rise) across the
        # configured window -- since a fall in either is the *helpful*
        # direction (less raw-material moisture, not more), neither should
        # be reported as if it explained the rising thermal SEC.
        investigation = investigate_root_cause("Plant B", "specific_thermal_energy_consumption_gj_per_t_clinker")
        assert not any("rainfall_mm" in c for c in investigation.contributing_factors)
        assert not any("avg_humidity_pct" in c for c in investigation.contributing_factors)

    def test_not_applied_when_thermal_energy_is_not_a_notable_driver(self):
        # The external-factor scan is gated on thermal energy itself being
        # a notable driver in *this* investigation. Plant C's thermal SEC
        # moves under 2% here (not notable), and its waste generation trend
        # has no plausible causal link to fuel ash/moisture anyway -- so no
        # external factor should be reported.
        investigation = investigate_root_cause("Plant C", "waste_generated_tonnes")
        assert investigation.trend == "increasing"
        assert not any(c.startswith("External factor:") for c in investigation.contributing_factors)


@dataclass
class _FakeTextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class _FakeLLMResponse:
    content: list[Any] = field(default_factory=list)


class _ScriptedLLMClient:
    def __init__(self, response_text: str):
        self._text = response_text
        self.calls: list[dict[str, Any]] = []

    def create_message(self, **kwargs: Any) -> _FakeLLMResponse:
        self.calls.append(kwargs)
        return _FakeLLMResponse(content=[_FakeTextBlock(text=self._text)])


class _RaisingLLMClient:
    def create_message(self, **kwargs: Any):
        raise ConnectionError("simulated network failure")


class TestLLMAssistedExploration:
    """The optional, genuinely open-ended stage -- only exercised here via
    an injected scripted client (`llm_client_override`), exactly like
    app.agent.llm_client's own tests. No network access or API key needed.
    """

    def test_adds_a_genuinely_new_hypothesis_from_the_scripted_client(self):
        client = _ScriptedLLMClient(
            '[{"statement": "The plant may have switched to a lower-grade limestone source, raising free lime and kiln burning temperature requirements.", "confidence": "Low"}]'
        )
        investigation = investigate_root_cause(
            "Plant B", "specific_thermal_energy_consumption_gj_per_t_clinker", llm_client_override=client,
        )
        llm_hypotheses = [f for f in investigation.findings if "limestone" in f.statement]
        assert len(llm_hypotheses) == 1
        assert llm_hypotheses[0].kind == "Hypothesis"
        assert llm_hypotheses[0].confidence == "Low"
        assert "LLM-identified additional hypothesis" in investigation.contributing_factors
        assert len(client.calls) == 1  # actually invoked

    def test_empty_array_response_adds_nothing(self):
        client = _ScriptedLLMClient("[]")
        investigation = investigate_root_cause(
            "Plant B", "specific_thermal_energy_consumption_gj_per_t_clinker", llm_client_override=client,
        )
        assert "LLM-identified additional hypothesis" not in investigation.contributing_factors

    def test_malformed_json_response_degrades_gracefully(self):
        client = _ScriptedLLMClient("not valid json at all")
        investigation = investigate_root_cause(
            "Plant B", "specific_thermal_energy_consumption_gj_per_t_clinker", llm_client_override=client,
        )
        # The deterministic findings must still be fully present.
        assert any("Kiln Refractory Lining" in f.statement for f in investigation.findings)
        assert "LLM-identified additional hypothesis" not in investigation.contributing_factors

    def test_network_failure_does_not_break_the_deterministic_result(self):
        investigation = investigate_root_cause(
            "Plant B", "specific_thermal_energy_consumption_gj_per_t_clinker",
            llm_client_override=_RaisingLLMClient(),
        )
        assert investigation.trend == "increasing"
        assert any("Kiln Refractory Lining" in f.statement for f in investigation.findings)

    def test_confidence_high_from_the_model_is_rejected(self):
        # A Hypothesis is by definition unconfirmed -- the parser must
        # refuse to accept "High" confidence even if the model returns it.
        client = _ScriptedLLMClient('[{"statement": "Some overclaimed cause.", "confidence": "High"}]')
        investigation = investigate_root_cause(
            "Plant B", "specific_thermal_energy_consumption_gj_per_t_clinker", llm_client_override=client,
        )
        assert not any("overclaimed" in f.statement for f in investigation.findings)

    def test_no_override_and_no_api_key_is_a_no_op(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        investigation = investigate_root_cause("Plant B", "specific_thermal_energy_consumption_gj_per_t_clinker")
        assert "LLM-identified additional hypothesis" not in investigation.contributing_factors
