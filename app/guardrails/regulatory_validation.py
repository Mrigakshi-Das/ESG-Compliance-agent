"""Guardrail #4: regulatory version control.

A regulation is never treated as current merely because it exists in the
knowledge base. `app.regulations.schema.RegulatoryRequirement` already
carries every field this classification needs (`status`,
`superseded_or_amended_by`, `effective_date`, `source_date`,
`last_reviewed`, `confidence`) -- this module is the missing decision
step that actually looks at all of them together before a caller is
allowed to treat the requirement as settled.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.guardrails.schemas import RegulatoryVersionStatus


def classify_regulatory_version(
    requirement: Any,
    as_of: str,
    staleness_days: int = 365,
) -> tuple[RegulatoryVersionStatus, str]:
    """Classify one `RegulatoryRequirement` (or an equivalent dict with the
    same fields) as CURRENT / OUTDATED / FUTURE_EFFECTIVE / UNKNOWN as of
    `as_of` (an ISO date string), plus a one-line reason.

    Order of checks (first match wins -- most conclusive fact first):
    1. Explicitly superseded/amended, or status == "Superseded" -> OUTDATED.
    2. status == "Draft/Proposed" -> FUTURE_EFFECTIVE (not yet in force)
       if its effective_date is in the future, else UNKNOWN (a draft with
       no forward effective date is not usable as current guidance).
    3. effective_date is after `as_of` -> FUTURE_EFFECTIVE.
    4. status == "Under Amendment" -> UNKNOWN (actively changing; a
       specific version cannot be asserted as settled).
    5. The KB record itself hasn't been reviewed in over `staleness_days`
       -> UNKNOWN (not OUTDATED -- staleness of *our review*, not proof the
       regulation itself changed, but it must not be silently trusted either).
    6. status == "Active", reviewed recently, effective now -> CURRENT.
    7. Anything else -> UNKNOWN.
    """
    def get(field: str) -> Any:
        return requirement[field] if isinstance(requirement, dict) else getattr(requirement, field)

    status = get("status")
    superseded_by = get("superseded_or_amended_by")
    effective_date = get("effective_date")
    last_reviewed = get("last_reviewed")

    if superseded_by or status == "Superseded":
        return "OUTDATED", f"Superseded/amended by {superseded_by!r}." if superseded_by else "Marked Superseded in the knowledge base."

    is_future = _is_future(effective_date, as_of)

    if status == "Draft/Proposed":
        if is_future:
            return "FUTURE_EFFECTIVE", f"Draft/Proposed, effective {effective_date} (not yet in force)."
        return "UNKNOWN", "Draft/Proposed with no confirmed future effective date -- not usable as current guidance."

    if is_future:
        return "FUTURE_EFFECTIVE", f"Effective date {effective_date} is after the assessment date {as_of}."

    if status == "Under Amendment":
        return "UNKNOWN", "Marked Under Amendment -- a specific current version cannot be asserted as settled."

    if _is_stale(last_reviewed, as_of, staleness_days):
        return "UNKNOWN", f"Knowledge-base record last reviewed {last_reviewed}, over {staleness_days} days before {as_of} -- currency not confirmed."

    if status == "Active":
        return "CURRENT", f"Active, effective {effective_date}, reviewed {last_reviewed}."

    return "UNKNOWN", f"Requirement status {status!r} does not establish it as current."


def _is_future(effective_date: str, as_of: str) -> bool:
    return date.fromisoformat(effective_date) > date.fromisoformat(as_of)


def _is_stale(last_reviewed: str, as_of: str, staleness_days: int) -> bool:
    return (date.fromisoformat(as_of) - date.fromisoformat(last_reviewed)).days > staleness_days


def requires_human_review(version_status: RegulatoryVersionStatus) -> bool:
    """Guardrail #4's rule: only a confirmed CURRENT status lets the agent
    make a definitive compliance conclusion. Everything else needs human
    verification before that conclusion can be made."""
    return version_status != "CURRENT"
