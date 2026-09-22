"""Enterprise guardrail layer: makes the agent "safely autonomous."

This package does not reimplement data retrieval, calculation, or
compliance logic -- `app.tools`, `app.calculations`, `app.compliance`, and
`app.regulations` already do that, deterministically, and already refuse to
fabricate a value (see their own module docstrings). What was missing was a
single, reusable, *programmatically enforceable* place where those existing
signals (a tool's `status`, a calculation's `CalculationError`, a
requirement's `last_reviewed` date, an evidence assessment's status) get
turned into structured guardrail decisions, logged as a queryable event
trail, and checked before a final answer ever reaches the user.

Modules
-------
schemas.py               Typed dataclasses and status vocabularies shared
                          by every other module here (GuardrailStatus,
                          GuardrailEvent, Provenance, ConfidenceAssessment,
                          ActionRequest, DataQualityScore, CalculationResult).
data_integrity.py         Wraps a tool result into a provenance-tagged
                          value and classifies it DATA_OK / DATA_MISSING /
                          DATA_CONFLICT / DATA_ANOMALY.
source_validation.py      Tier 1/2/3 classification for a regulatory or
                          evidence source.
regulatory_validation.py  CURRENT / OUTDATED / FUTURE_EFFECTIVE / UNKNOWN
                          status for a RegulatoryRequirement, from its
                          existing version-control fields.
calculation_safety.py     Wraps a deterministic calculation call into a
                          structured, provenance-carrying result and
                          rejects out-of-range/duplicate/incompatible
                          inputs before the calculation ever runs.
evidence_validation.py    Maps app.tools.evidence's evidence_status values
                          onto the EVIDENCE_* vocabulary and enforces "no
                          evidence != compliant".
confidence.py              Transparent, multi-factor HIGH/MEDIUM/LOW
                          confidence -- never a bare LLM-claimed number.
action_authorization.py    LEVEL_1 / LEVEL_2 / LEVEL_3 action
                          classification and the ACTION_REQUIRES_APPROVAL
                          gate for anything consequential.
stop_conditions.py         Centralizes every reason the agent is allowed
                          (and required) to stop rather than guess.
output_validation.py       The last checkpoint before a response reaches
                          the user: every numeric claim has provenance,
                          every compliance claim is properly hedged, no
                          prohibited action was executed.
engine.py                  `GuardrailEngine` -- the single object the
                          orchestrator talks to; ties every module above
                          together and owns the per-run event log.

None of this is prompt-level guidance. Every guardrail here is a plain
Python function/class enforcing a typed status, testable in isolation and
without any LLM in the loop -- see app/tests/test_guardrails_*.py.
"""
