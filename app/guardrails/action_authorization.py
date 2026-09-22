"""Guardrail #10: action authorization.

This system today only ever *reads* plant data and regulatory sources and
*writes* a report -- it has no email, ticketing, or regulatory-submission
integration (see docs/KNOWN_LIMITATIONS.md). That is precisely why this
module exists: the moment such a capability is added, every consequential
action must already be routed through here first, rather than that check
being invented under deadline pressure at integration time. Until then,
this module's job is to recognize when a *user's request itself* is asking
for a Level 3 action, and refuse to execute it -- returning
ACTION_REQUIRES_APPROVAL instead of silently doing nothing or, worse,
inventing a response that implies it happened.
"""

from __future__ import annotations

from app.guardrails.schemas import ActionLevel, ActionRequest

# Consequential / external actions -- always Level 3, always
# ACTION_REQUIRES_APPROVAL, regardless of how the request is phrased.
# Kept as short, unambiguous noun-phrases (matching this project's existing
# rule-based keyword style in app.agent.planner) rather than exact
# sentences, so a real variety of phrasing for the same consequential
# action is still caught -- see app/tests/test_guardrails_action_
# authorization.py for the phrasings this is tested against.
_LEVEL_3_KEYWORDS = (
    "work order", "maintenance ticket",
    "escalation email", "send an email", "escalate to", "notify the regulator", "notify regulator",
    "operating parameter", "kiln setting", "plant setting",
    "source record", "source data", "source production record", "overwrite source", "correct the source", "edit the source", "modify the source",
    "regulatory report", "submit to the regulator", "submit to cpcb", "submit to bee", "submit to sebi",
    "file with the regulator", "send information to", "send data to the regulator",
    "financial expenditure", "approve expenditure", "authorize spending", "approve budget", "financial commitment",
)

# Explicit recommendation-shaped requests -- generated automatically, but
# never executed; distinguished from Level 3 mainly by not being
# irreversible or external.
_LEVEL_2_KEYWORDS = (
    "recommend", "suggest a fix", "suggest maintenance", "propose a correction",
)


def classify_action(description: str) -> ActionLevel:
    """Classify a requested or described action into LEVEL_1_INFORMATIONAL
    (read data, calculate, compare, analyze -- runs automatically),
    LEVEL_2_RECOMMENDATION (generated automatically, never executed
    externally), or LEVEL_3_CONSEQUENTIAL (requires explicit human
    approval before anything happens). Keyword-based, matching this
    project's existing rule-based intent classifier in
    `app.agent.planner` rather than an LLM judgment call -- so this check
    is itself deterministic and testable without a model in the loop."""
    lower = description.lower()
    if any(k in lower for k in _LEVEL_3_KEYWORDS):
        return "LEVEL_3_CONSEQUENTIAL"
    if any(k in lower for k in _LEVEL_2_KEYWORDS):
        return "LEVEL_2_RECOMMENDATION"
    return "LEVEL_1_INFORMATIONAL"


def authorize_action(description: str, approved: bool = False) -> ActionRequest:
    """Build the ActionRequest for a described action. Level 3 actions
    always carry `requires_approval=True`; the agent must never execute
    one where `requires_approval and not approved` -- see
    `app.guardrails.engine.GuardrailEngine.check_action` for the
    enforcement point, and `app.agent.orchestrator`'s
    `external_action_request` intent for where a user's own request gets
    routed here instead of silently doing nothing or fabricating a
    "done" response."""
    level = classify_action(description)
    requires_approval = level == "LEVEL_3_CONSEQUENTIAL"
    return ActionRequest(
        action=description, level=level, description=description,
        requires_approval=requires_approval, approved=approved and requires_approval,
    )
