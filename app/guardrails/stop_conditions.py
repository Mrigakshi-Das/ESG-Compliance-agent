"""Guardrail #12: stop conditions.

Centralizes every reason the agent is allowed -- and required -- to stop
rather than guess. The orchestrator already refuses to fabricate a final
answer when nothing was produced (`MISSING_DATA_MESSAGE`); this module
generalizes that into a single, reusable check covering every stop
condition the brief names, so a new intent handler gets this behavior for
free instead of re-deriving "should I even try to answer" by hand.
"""

from __future__ import annotations

from app.guardrails.schemas import GuardrailStatus, StopDecision

_BLOCKING_DATA_STATUSES = {"DATA_MISSING", "DATA_CONFLICT"}
_BLOCKING_CALCULATION_STATUS = "BLOCKED"


def should_stop(
    *,
    required_data_missing: bool = False,
    critical_data_conflict: bool = False,
    regulatory_source_unvalidated: bool = False,
    calculation_validation_failed: bool = False,
    evidence_insufficient: bool = False,
    action_requires_authorization: bool = False,
) -> StopDecision:
    """Each keyword argument names one stop condition the brief lists
    explicitly. All default False (nothing wrong); the first True one
    found determines the reported reason (a run can have more than one
    problem, but the user only needs the first honest explanation, not an
    exhaustive dump -- the full detail lives in the guardrail event log
    either way)."""
    if required_data_missing:
        return StopDecision(True, "Required data is unavailable for this assessment.")
    if critical_data_conflict:
        return StopDecision(True, "Critical data conflict exists between sources; a reliable answer cannot be produced without human verification.")
    if regulatory_source_unvalidated:
        return StopDecision(True, "The applicable regulatory source could not be validated as current.")
    if calculation_validation_failed:
        return StopDecision(True, "A required calculation failed input validation.")
    if evidence_insufficient:
        return StopDecision(True, "Evidence is insufficient to support the requested conclusion.")
    if action_requires_authorization:
        return StopDecision(True, "The requested action requires explicit human authorization before it can proceed.")
    return StopDecision(False, None)


def classify_and_check(data_statuses: list[GuardrailStatus]) -> StopDecision:
    """Convenience entry point for the common case: given the DATA_* status
    of every tool call an intent needed, decide whether to stop. A single
    DATA_MISSING or DATA_CONFLICT among required inputs is enough --
    DATA_ANOMALY alone does not force a stop (an anomaly is flagged, not
    necessarily fatal; see data_integrity.py), matching the design
    principle that guardrails should block only what is genuinely
    unreliable, not everything unusual."""
    if any(s in _BLOCKING_DATA_STATUSES for s in data_statuses):
        missing = "DATA_MISSING" in data_statuses
        conflict = "DATA_CONFLICT" in data_statuses
        return should_stop(required_data_missing=missing, critical_data_conflict=conflict)
    return StopDecision(False, None)
