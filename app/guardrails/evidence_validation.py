"""Guardrail #7: evidence required, and "no evidence != compliant".

`app.tools.evidence.assess_evidence` already computes a real evidence
status ("Compliant", "Missing", "Outdated", "Conflicting", "Mixed") from
the actual document repository -- this module maps that onto the
guardrail's typed EVIDENCE_* vocabulary and enforces the one rule most
worth enforcing structurally rather than trusting to prose: a missing
calibration certificate must never render as "Calibration is compliant."
"""

from __future__ import annotations

from typing import Any

from app.guardrails.schemas import ConfidenceLevel, EvidenceFinding, GuardrailStatus

_STATUS_MAP: dict[str, GuardrailStatus] = {
    "Compliant": "EVIDENCE_VERIFIED",
    "Missing": "EVIDENCE_MISSING",
    "Outdated": "EVIDENCE_OUTDATED",
    "Conflicting": "EVIDENCE_CONFLICT",
    "Mixed": "EVIDENCE_MISSING",  # partially covered -- still can't call it verified
}

_HUMAN_REVIEW_STATUSES = {"EVIDENCE_MISSING", "EVIDENCE_OUTDATED", "EVIDENCE_INVALID", "EVIDENCE_CONFLICT"}


def classify_evidence_status(raw_evidence_status: str) -> GuardrailStatus:
    """Map assess_evidence's existing status string onto the typed
    EVIDENCE_* vocabulary. An unrecognized status is classified
    EVIDENCE_INVALID rather than silently passed through -- an evidence
    tool returning something outside its own documented vocabulary is
    itself a data-quality problem, not something to guess about."""
    return _STATUS_MAP.get(raw_evidence_status, "EVIDENCE_INVALID")


def build_evidence_finding(
    finding: str,
    evidence_result: dict[str, Any],
    assessment_period: str | None,
    evidence_source: str | None = None,
    evidence_date: str | None = None,
) -> EvidenceFinding:
    """Build the structured EvidenceFinding guardrail #7 specifies. Never
    reports a compliant/verified status unless assess_evidence's own
    evidence_status is literally "Compliant" -- everything else (Missing,
    Outdated, Conflicting, Mixed, or an unrecognized value) maps to a
    non-verified EVIDENCE_* status and `human_review_required=True`, which
    is exactly the enforcement "no evidence != compliant" needs: there is
    no code path where absence of evidence produces a compliant result."""
    raw_status = evidence_result.get("evidence_status", "")
    status = classify_evidence_status(raw_status)
    confidence: ConfidenceLevel = "HIGH" if status == "EVIDENCE_VERIFIED" else "LOW"
    return EvidenceFinding(
        finding=finding,
        evidence_status=status,
        evidence_source=evidence_source,
        evidence_date=evidence_date,
        assessment_period=assessment_period,
        confidence=confidence,
        human_review_required=status in _HUMAN_REVIEW_STATUSES,
    )


def safe_evidence_statement(finding: EvidenceFinding, subject: str) -> str:
    """Render a status-appropriate sentence for an evidence finding --
    guardrail #7's worked example ("Calibration evidence was not found...
    Compliance status cannot be verified.") as a reusable function instead
    of prose an orchestrator handler has to get right by hand each time."""
    if finding.evidence_status == "EVIDENCE_VERIFIED":
        return f"{subject}: supporting evidence was found and verified."
    if finding.evidence_status == "EVIDENCE_MISSING":
        return f"{subject}: evidence was not found. Compliance status cannot be verified."
    if finding.evidence_status == "EVIDENCE_OUTDATED":
        return f"{subject}: the evidence on file has expired or is outdated. Compliance status cannot be verified as current."
    if finding.evidence_status == "EVIDENCE_CONFLICT":
        return f"{subject}: conflicting evidence records were found. Compliance status cannot be verified until the conflict is resolved."
    return f"{subject}: evidence status could not be determined ({finding.evidence_status}). Compliance status cannot be verified."
