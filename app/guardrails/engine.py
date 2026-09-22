"""The single object `app.agent.orchestrator` talks to for every guardrail
decision -- ties together data_integrity, source_validation,
regulatory_validation, calculation_safety, evidence_validation,
confidence, action_authorization, stop_conditions, and output_validation,
and owns the per-run structured event log (guardrail architecture item 19).

One `GuardrailEngine` instance per agent run (created fresh in `run()`,
same lifetime as the `AgentRunState` it augments -- see
`app.agent.state.AgentRunState.guardrail_events`, which is populated from
`engine.events` at the end of the run).

    User Query
        |
        v
    Agent Orchestrator
        |
        v
    Guardrail Pre-Check      <- GuardrailEngine.check_stop (before acting)
        |
        v
    Tool Selection
        |
        v
    Tool Execution
        |
        v
    Tool Output Validation   <- GuardrailEngine.check_tool_result
        |
        v
    Guardrail Post-Check     <- check_evidence / check_regulatory_version /
        |                        check_calculation / assess_confidence
        v
    Decision / Escalation    <- check_action / check_stop
        |
        v
    Final Response           <- GuardrailEngine.validate_output
"""

from __future__ import annotations

from typing import Any, Callable

from app.guardrails import (
    action_authorization,
    calculation_safety,
    confidence as confidence_mod,
    data_integrity,
    evidence_validation,
    output_validation,
    regulatory_validation,
    stop_conditions,
)
from app.guardrails.schemas import (
    ActionRequest,
    CalculationResult,
    ConfidenceAssessment,
    DataQualityScore,
    EvidenceFinding,
    GuardrailEvent,
    GuardrailStatus,
    Provenance,
    RegulatoryVersionStatus,
    Severity,
    StopDecision,
)

_SEVERITY_BY_DATA_STATUS: dict[GuardrailStatus, Severity] = {
    "DATA_MISSING": "HIGH",
    "DATA_CONFLICT": "HIGH",
    "DATA_ANOMALY": "MEDIUM",
}
_ACTION_BY_DATA_STATUS = {
    "DATA_MISSING": "BLOCK_CALCULATION",
    "DATA_CONFLICT": "BLOCK_CALCULATION",
    "DATA_ANOMALY": "FLAG_FOR_REVIEW",
}


class GuardrailEngine:
    def __init__(self) -> None:
        self.events: list[GuardrailEvent] = []
        # Signals accumulated across the run, feeding assess_run_confidence.
        self._data_statuses: list[GuardrailStatus] = []
        self._evidence_statuses: list[GuardrailStatus] = []
        self._regulatory_statuses: list[RegulatoryVersionStatus] = []
        self._calculation_statuses: list[str] = []
        self._source_tiers: list[str] = []
        self.pending_actions: list[ActionRequest] = []

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(
        self,
        guardrail: str,
        severity: Severity,
        reason: str,
        action: str,
        metric: str | None = None,
        sources: list[str] | None = None,
        human_review_required: bool = False,
    ) -> GuardrailEvent:
        event = GuardrailEvent(
            guardrail=guardrail, severity=severity, reason=reason, action=action,
            metric=metric, sources=sources or [], human_review_required=human_review_required,
        )
        self.events.append(event)
        return event

    # ------------------------------------------------------------------
    # Guardrail #1 / #2 / #8 -- tool output validation
    # ------------------------------------------------------------------

    def check_tool_result(self, tool_name: str, result: dict[str, Any] | None) -> GuardrailStatus:
        status = data_integrity.classify_tool_result(tool_name, result)
        self._data_statuses.append(status)

        if status == "DATA_CONFLICT" and isinstance(result, dict):
            conflict = data_integrity.build_data_conflict(tool_name, result)
            self.log(
                "DATA_CONFLICT", "HIGH",
                conflict.impact if conflict else f"{tool_name} returned conflicting values.",
                "BLOCK_CALCULATION", metric=conflict.metric if conflict else tool_name,
                sources=[v.source for v in conflict.values] if conflict else [],
                human_review_required=True,
            )
        elif status == "DATA_MISSING":
            self.log(
                "DATA_MISSING", "HIGH", f"{tool_name} returned no usable data.",
                "BLOCK_CALCULATION", metric=tool_name,
            )
        elif status == "DATA_ANOMALY":
            self.log(
                "DATA_ANOMALY", "MEDIUM", f"{tool_name} returned an anomalous or duplicated value.",
                "FLAG_FOR_REVIEW", metric=tool_name,
            )
        return status

    def data_conflict_detail(self, tool_name: str, result: dict[str, Any]) -> dict[str, Any] | None:
        conflict = data_integrity.build_data_conflict(tool_name, result)
        return conflict.as_dict() if conflict else None

    def score_data_quality(self, report: Any) -> DataQualityScore:
        return data_integrity.score_data_quality(report)

    # ------------------------------------------------------------------
    # Guardrail #3 / #4 -- regulatory source and version validation
    # ------------------------------------------------------------------

    def check_regulatory_version(self, requirement: Any, as_of: str) -> tuple[RegulatoryVersionStatus, str]:
        status, reason = regulatory_validation.classify_regulatory_version(requirement, as_of)
        self._regulatory_statuses.append(status)
        if status != "CURRENT":
            severity: Severity = "HIGH" if status == "OUTDATED" else "MEDIUM"
            self.log(
                f"REGULATION_{status}", severity, reason,
                "REQUIRE_HUMAN_REVIEW" if regulatory_validation.requires_human_review(status) else "NOTE",
                human_review_required=regulatory_validation.requires_human_review(status),
            )
        return status, reason

    def check_source_tier(self, authority: str | None, source_description: str | None = None) -> str:
        from app.guardrails import source_validation

        tier = source_validation.classify_source(authority, source_description)
        self._source_tiers.append(tier)
        if tier == "TIER_3_SECONDARY":
            self.log(
                "REGULATION_UNCERTAIN", "MEDIUM",
                f"Source {authority or source_description!r} is Tier 3 (secondary) and cannot alone support a compliance conclusion.",
                "FLAG_FOR_REVIEW", human_review_required=True,
            )
        return tier

    # ------------------------------------------------------------------
    # Guardrail #6 -- deterministic calculation safety
    # ------------------------------------------------------------------

    def check_calculation(
        self, fn: Callable[..., float], formula: str, units: str,
        inputs: dict[str, Any], provenance: dict[str, Provenance],
    ) -> CalculationResult:
        result = calculation_safety.safe_calculate(fn, formula, units, inputs, provenance)
        self._calculation_statuses.append(result.validation_status)
        if result.validation_status == "BLOCKED":
            self.log(
                "CALCULATION_BLOCKED", "HIGH",
                result.rejection_reason or "Calculation input validation failed.",
                "BLOCK_CALCULATION", metric=formula,
            )
        return result

    # ------------------------------------------------------------------
    # Guardrail #7 -- evidence required
    # ------------------------------------------------------------------

    def check_evidence(
        self, finding: str, evidence_result: dict[str, Any], assessment_period: str | None,
        evidence_source: str | None = None, evidence_date: str | None = None,
    ) -> EvidenceFinding:
        ev = evidence_validation.build_evidence_finding(finding, evidence_result, assessment_period, evidence_source, evidence_date)
        self._evidence_statuses.append(ev.evidence_status)
        if ev.human_review_required:
            self.log(
                ev.evidence_status, "MEDIUM", ev.finding, "FLAG_FOR_REVIEW",
                human_review_required=True,
            )
        return ev

    # ------------------------------------------------------------------
    # Guardrail #10 -- action authorization
    # ------------------------------------------------------------------

    def check_action(self, description: str, approved: bool = False) -> ActionRequest:
        action = action_authorization.authorize_action(description, approved=approved)
        if action.requires_approval and not action.approved:
            self.pending_actions.append(action)
            self.log(
                "ACTION_REQUIRES_APPROVAL", "CRITICAL",
                f"Requested action is Level 3 (consequential) and was not executed: {description}",
                "REQUIRE_APPROVAL", human_review_required=True,
            )
        return action

    # ------------------------------------------------------------------
    # Guardrail #12 -- stop conditions
    # ------------------------------------------------------------------

    def check_stop(self, **kwargs: bool) -> StopDecision:
        decision = stop_conditions.should_stop(**kwargs)
        if decision.should_stop:
            self.log("STOP_CONDITION", "HIGH", decision.reason or "Stop condition met.", "STOP")
        return decision

    def check_stop_for_data(self) -> StopDecision:
        """Convenience: stop-check driven by every DATA_* status recorded
        so far via check_tool_result."""
        return stop_conditions.classify_and_check(self._data_statuses)

    # ------------------------------------------------------------------
    # Guardrail #13 -- confidence
    # ------------------------------------------------------------------

    def assess_confidence(self) -> ConfidenceAssessment:
        """Confidence for the run so far, from every signal recorded
        through this engine -- never a value the caller supplies directly."""
        return confidence_mod.assess_confidence(
            data_statuses=self._data_statuses,
            evidence_statuses=self._evidence_statuses,
            regulatory_statuses=self._regulatory_statuses,
            calculation_statuses=self._calculation_statuses,
            source_tiers=self._source_tiers,
        )

    # ------------------------------------------------------------------
    # Guardrail #14 -- output validation
    # ------------------------------------------------------------------

    def validate_output(self, raw_query: str, final_answer: str | None, human_review_required: bool):
        result = output_validation.validate_output(
            raw_query, final_answer, self.events, human_review_required, self.pending_actions,
        )
        if not result.passed:
            self.log(
                "OUTPUT_VALIDATION_FAILED", "CRITICAL", "; ".join(result.violations),
                "BLOCK_RESPONSE", human_review_required=True,
            )
        return result

    # ------------------------------------------------------------------
    # Aggregate views -- what the orchestrator/UI actually read back
    # ------------------------------------------------------------------

    @property
    def human_review_required(self) -> bool:
        return any(e.human_review_required for e in self.events)

    @property
    def human_review_reasons(self) -> list[str]:
        seen: list[str] = []
        for e in self.events:
            if e.human_review_required and e.reason not in seen:
                seen.append(e.reason)
        return seen

    @property
    def approval_required(self) -> bool:
        return any(a.requires_approval and not a.approved for a in self.pending_actions)

    def events_as_dicts(self) -> list[dict[str, Any]]:
        return [e.as_dict() for e in self.events]

    def dashboard(self, data_quality_score: DataQualityScore | None = None) -> dict[str, Any]:
        """Payload for the UI's "Guardrails & Reliability" panel -- the
        four progress-bar metrics, the human-review flag, and the most
        recent events, all derived from what this engine actually recorded
        during the run (never a fabricated display value)."""
        evidence_verified = sum(1 for s in self._evidence_statuses if s == "EVIDENCE_VERIFIED")
        evidence_total = len(self._evidence_statuses)
        evidence_coverage_pct = round(evidence_verified / evidence_total * 100, 1) if evidence_total else 100.0

        regulatory_current = sum(1 for s in self._regulatory_statuses if s == "CURRENT")
        regulatory_total = len(self._regulatory_statuses)
        regulatory_validity_pct = round(regulatory_current / regulatory_total * 100, 1) if regulatory_total else 100.0

        calc_passed = sum(1 for s in self._calculation_statuses if s == "PASSED")
        calc_total = len(self._calculation_statuses)
        calculation_validation_pct = round(calc_passed / calc_total * 100, 1) if calc_total else 100.0

        return {
            "data_integrity_pct": data_quality_score.overall if data_quality_score else None,
            "evidence_coverage_pct": evidence_coverage_pct,
            "regulatory_source_validity_pct": regulatory_validity_pct,
            "calculation_validation_pct": calculation_validation_pct,
            "human_review_required": self.human_review_required,
            "human_review_reasons": self.human_review_reasons,
            "approval_required": self.approval_required,
            "recent_events": [e.as_dict() for e in self.events[-10:]],
            "total_events": len(self.events),
        }
