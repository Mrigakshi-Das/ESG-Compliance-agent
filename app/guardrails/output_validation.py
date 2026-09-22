"""Guardrail #14: output validation -- the last checkpoint before a
response reaches the user.

Every number in this system already comes from a registered tool or a
deterministic calculation by construction (see app.tools and
app.calculations); this module's job is not to re-derive that guarantee,
it is to catch the two failure modes that construction alone cannot
prevent: (1) a final-answer sentence that overstates certainty in plain
English even though the underlying data was honestly labeled uncertain
(a stark "is legally compliant" claim), and (2) a guardrail signal (a
conflict, a required approval) that was recorded internally but never
actually surfaced to the reader.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.guardrails.schemas import ActionRequest, GuardrailEvent

_LEGAL_COMPLIANCE_TRIGGERS = (
    "legally compliant", "legal compliance", "fully compliant with the law",
    "is the plant compliant", "is compliant with", "in compliance with the law",
)
_HEDGE_PHRASES = (
    "readiness", "not a determination of legal compliance", "potential gap",
    "human review", "cannot be calculated", "cannot be verified", "requires approval",
)

DISCLAIMER = (
    "This is a compliance-readiness assessment based on the regulatory knowledge base "
    "configured in this system. It is not a determination of legal compliance."
)


@dataclass
class OutputValidationResult:
    passed: bool
    violations: list[str] = field(default_factory=list)
    safe_response: str | None = None

    def as_dict(self) -> dict:
        return {"passed": self.passed, "violations": self.violations, "safe_response": self.safe_response}


def _overstates_legal_compliance(raw_query: str, final_answer: str) -> bool:
    query_l = raw_query.lower()
    answer_l = final_answer.lower()
    asked_about_legal_compliance = any(t in query_l for t in _LEGAL_COMPLIANCE_TRIGGERS)
    if not asked_about_legal_compliance:
        return False
    return not any(h in answer_l for h in _HEDGE_PHRASES)


def validate_output(
    raw_query: str,
    final_answer: str | None,
    guardrail_events: list[GuardrailEvent],
    human_review_required: bool,
    pending_actions: list[ActionRequest] | None = None,
) -> OutputValidationResult:
    """Run every guardrail #14 check against a response that's about to be
    returned. A `None` final_answer (a safe stop -- guardrail #12) always
    passes: refusing to answer is never a validation failure, it's the
    correct behavior this whole layer exists to protect."""
    if final_answer is None:
        return OutputValidationResult(passed=True)

    pending_actions = pending_actions or []
    violations: list[str] = []

    if _overstates_legal_compliance(raw_query, final_answer):
        violations.append(
            "Response answers a legal-compliance question without the required compliance-readiness qualification."
        )

    conflict_events = [e for e in guardrail_events if "CONFLICT" in e.guardrail]
    if conflict_events and not human_review_required:
        violations.append(
            f"{len(conflict_events)} conflict guardrail event(s) were recorded but human_review_required is False -- "
            "a disclosed conflict must always require human review."
        )

    unapproved = [a for a in pending_actions if a.requires_approval and not a.approved]
    for action in unapproved:
        claim_words = ("has been submitted", "has been sent", "has been completed", "was submitted", "was sent")
        if any(w in final_answer.lower() for w in claim_words):
            violations.append(
                f"Response implies the unapproved Level 3 action {action.action!r} was executed."
            )

    if violations:
        safe_response = (
            "This response could not be returned as generated because it did not pass output validation: "
            + "; ".join(violations)
            + f" {DISCLAIMER}"
        )
        return OutputValidationResult(passed=False, violations=violations, safe_response=safe_response)

    return OutputValidationResult(passed=True)


def ensure_compliance_disclaimer(final_answer: str, raw_query: str) -> str:
    """If the query asked about legal compliance and the answer doesn't
    already carry a hedge, append the standard disclaimer rather than
    blocking outright -- used by the orchestrator to self-correct before
    validate_output would otherwise have to fail the response."""
    if _overstates_legal_compliance(raw_query, final_answer):
        return f"{final_answer} {DISCLAIMER}"
    return final_answer
