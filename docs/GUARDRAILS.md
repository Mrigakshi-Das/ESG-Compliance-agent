# Guardrails: Making the Agent Safely Autonomous

This document explains the enterprise guardrail layer added in Phase 12 —
what it enforces, how it's architected, and how it plugs into the existing
agent without duplicating or weakening anything that was already there.

The goal stated at the start of this phase was **safe autonomy, not no
autonomy**: the agent should still independently plan, retrieve data,
calculate metrics, identify gaps, investigate root causes, and recommend
actions — but every one of those steps now passes through explicit,
programmatically enforced checkpoints instead of relying on prompt-level
good behavior alone.

## Why a separate layer, not more `if/else`

Most of what guardrails need was **already true** by construction before
this phase — the project's founding discipline (see
[AI_AGENT_QUALIFICATION.md](AI_AGENT_QUALIFICATION.md)) was always "never
invent a number, never guess a regulatory fact, always label Fact vs.
Hypothesis." What was missing was a single, reusable, *testable* place
where those scattered signals (a tool's `status`, a `CalculationError`, a
requirement's `last_reviewed` date, an evidence status string) become
structured decisions, get logged as a queryable event trail, and get
checked one final time before a response reaches the user. `app/guardrails/`
is that place — nine focused modules plus an engine that ties them
together, none of which reimplement data retrieval, calculation, or
compliance logic that `app.tools` / `app.calculations` / `app.compliance` /
`app.regulations` already owned.

## Architecture

```
User Query
    |
    v
Agent Orchestrator
    |
    v
Guardrail Pre-Check          <- GuardrailEngine.check_stop
    |
    v
Tool Selection
    |
    v
Tool Execution
    |
    v
Tool Output Validation       <- GuardrailEngine.check_tool_result
    |                            (guardrails #1 / #2 / #8)
    v
Guardrail Post-Check         <- check_evidence / check_regulatory_version /
    |                            check_calculation / assess_confidence
    v
Decision / Escalation        <- check_action / human_review_required
    |
    v
Final Response                <- GuardrailEngine.validate_output
                                  (guardrail #14)
```

One `GuardrailEngine` instance is created per agent run (in
`app.agent.orchestrator.run`) and threaded through by attaching it to the
`AgentRunState` as `state._guardrail_engine` — a plain runtime attribute,
not a dataclass field, since it isn't JSON-serializable and nothing should
try to report it directly. `_call_tool`, the single chokepoint every
simple intent handler already calls through, retrieves it from `state` and
runs `check_tool_result` automatically — which means most handlers needed
**zero changes** to get guardrail coverage. `_execute_full_assessment` and
`_execute_evidence_audit`, which compose their own internal tool calls
through `app.compliance.engine` / `app.tools.evidence` directly (bypassing
`_call_tool` by original design), got explicit guardrail calls added at
their own aggregation points instead.

```
app/guardrails/
    __init__.py               Architecture overview (this file's source)
    schemas.py                 Every typed dataclass/status vocabulary
    data_integrity.py          Guardrails #1, #2, #8
    source_validation.py       Guardrail #3 (Tier 1/2/3 hierarchy)
    regulatory_validation.py   Guardrail #4 (CURRENT/OUTDATED/...)
    calculation_safety.py      Guardrail #6
    evidence_validation.py     Guardrail #7
    confidence.py              Guardrail #13
    action_authorization.py    Guardrail #10
    stop_conditions.py         Guardrail #12
    output_validation.py       Guardrail #14
    engine.py                  GuardrailEngine -- ties it all together
```

## The fourteen guardrails, and what already backed each one

| # | Guardrail | What already existed | What this phase added |
|---|---|---|---|
| 1 | No hallucinated data | Every value already traced to a registered tool; nothing was ever LLM-generated | `Provenance`/`ProvenancedValue` schemas, `DATA_MISSING` classification, anomaly detection (impossible negative/out-of-range values) |
| 2 | Data conflict detection | `app.tools._common.resolve_rows` already detected conflicting rows | The structured `DataConflict` object (guardrail spec's exact `{status, metric, values, impact, action}` shape) and a `DATA_CONFLICT` event on every tool call |
| 3 | Authoritative regulatory sources | Every KB record already named its `authority` (BEE, SEBI, CPCB/MoEFCC) | The Tier 1/2/3 classifier and the rule that Tier 3 alone can't support a compliance conclusion |
| 4 | Regulatory version control | `RegulatoryRequirement` already carried `status`, `superseded_or_amended_by`, `effective_date`, `last_reviewed` | The actual CURRENT/OUTDATED/FUTURE_EFFECTIVE/UNKNOWN decision that reads all of them together |
| 5 | No legal compliance claims | The fixed report disclaimer already existed | A runtime check on the literal final-answer text for a legal-compliance-phrased question, auto-appending the qualification if missing |
| 6 | Deterministic calculations | `app.calculations.*` already raised `CalculationError` on bad input; the LLM path could only ever call a registered tool | The structured `CalculationResult` wrapper and an incompatible-period/plant check before the arithmetic runs |
| 7 | Evidence required | `assess_evidence` already computed a real status from the document repository | The `EVIDENCE_*` typed vocabulary and the "no evidence != compliant" enforcement (a missing/outdated/conflicting status can never render as verified) |
| 8 | Data quality checks | `app.compliance.data_quality.DataQualityReport` already existed | The numeric 0-100 `DataQualityScore` (completeness/consistency/timeliness), explicitly never treated as proof of compliance |
| 9 | Human review | `human_review_required`/`human_review_reasons` already existed on `AgentRunState` | A structured trigger list feeding it (conflicts, evidence gaps, unvalidated sources, requested actions) merged with the pre-existing logic, not replacing it |
| 10 | Action authorization | Nothing — the system has never executed an external action | The full Level 1/2/3 classifier, the `external_action_request` intent, and the refusal to execute (or imply completion of) an unapproved Level 3 action |
| 11 | Source data immutability | Already true architecturally — every tool only ever reads `app/data` | Made explicit and testable: guardrails classify "modify source data" requests as Level 3, never executed |
| 12 | Stop conditions | `MISSING_DATA_MESSAGE` already existed for one case | Generalized to every named stop condition (data missing, critical conflict, unvalidated source, failed calculation, insufficient evidence, unauthorized action) |
| 13 | Confidence | A single `High`/`Medium`/`Low` scalar already existed | The five-factor transparent methodology (`ConfidenceAssessment`) computed from the signals above, never a bare claimed number |
| 14 | Output validation | Nothing checked the final answer text itself | `validate_output` — the last checkpoint before a response is returned, blocking/replacing it if a legal-compliance claim, an undisclosed conflict, or an implied-but-unapproved action slips through |

Guardrail #9 (Human Review) and #11 (Source Data Immutability) don't have
their own module by design — #9 is an aggregate property of every other
guardrail (see `GuardrailEngine.human_review_required`), and #11 was
already a structural property of the read-only tool architecture that
guardrail #10 makes enforceable the moment any write-capable action is
proposed.

## Two vocabularies, deliberately

`app.calculations.scoring.ComplianceStatus` ("Compliant", "Potential Gap",
"Data Missing", "Human Review Required", ...) already existed, is
extensively tested (59+ tests), and describes **one regulatory
requirement's compliance-readiness verdict**. `app.guardrails.schemas.
GuardrailStatus` ("DATA_OK", "DATA_CONFLICT", "EVIDENCE_MISSING",
"REGULATION_OUTDATED", ...) is a **separate, additive** vocabulary
describing the guardrail engine's own signals. They overlap in meaning at
points — a tool's `"conflict"` status and a `DATA_CONFLICT` guardrail event
describe the same underlying fact — and the mapping between them is
intentional, but nothing about adding the second vocabulary renamed or
repurposed the first. This was a deliberate choice to satisfy "maintain
backward compatibility" (Phase 12's own instruction #24.4) without leaving
the new guardrail layer speaking a vaguer language than the compliance
engine it wraps.

## What changed in the existing code, and why it's safe

- **`app/agent/state.py`** — 9 new fields on `AgentRunState`
  (`data_sources`, `regulatory_sources`, `conflicts`, `evidence`,
  `data_quality`, `confidence_assessment`, `guardrail_events`,
  `pending_actions`, `approval_required`), all with defaults, all purely
  additive. Nothing existing changed shape.
- **`app/agent/orchestrator.py`** — `_call_tool` and `_finalize` gained
  guardrail hooks; `_execute_full_assessment` and `_execute_evidence_audit`
  gained explicit evidence/regulatory-version checks; one new intent
  (`external_action_request`) and its handler were added. Every existing
  handler's own logic is untouched.
- **`app/agent/planner.py`** — two new keyword lists
  (`_EXTERNAL_ACTION_WORDS`, extended `_ASSESSMENT_WORDS`) and one new
  early-exit branch in `_classify_intent`. No existing intent's
  classification logic changed.
- **`app/ui/server.py` / `app/ui/static/*`** — new response fields and one
  new UI panel, additive to the existing response shape and layout.

291 tests passed before this phase (see [TEST_RESULTS.md](TEST_RESULTS.md)
for the running count); all of them still pass after it, unmodified,
proving the guardrail layer is additive rather than a rewrite. See
[TEST_RESULTS.md](TEST_RESULTS.md) for the current total including the new
guardrail tests.

## Known limitations of this phase

- **Guardrail #10 has no real action to authorize yet.** This system has
  never sent an email, filed a report, or written to a source system —
  guardrail #10 exists so that the moment such a capability is added, it's
  already routed through an approval gate rather than that check being
  invented under deadline pressure. Until then, "action requires approval"
  is demonstrated by refusing requests phrased as one (see
  [DEMO.md](DEMO.md)'s guardrail scenarios), not by gating a live
  integration.
- **Source-tier classification is keyword-based**, matching this project's
  existing rule-based style everywhere else (the intent planner, the
  metric-keyword mapper). A source description phrased unusually could be
  misclassified; see `app/guardrails/source_validation.py`'s own docstring
  for the specific substring-matching trade-off this makes (and the
  false-positive bug already found and fixed during this phase's own
  testing — an authority field with a full official name required a
  substring match, not exact equality, once tested against the real KB).
- **The data-quality score's "timeliness" sub-score is a heuristic**
  (flagged-issue count), not a measurement against a live ingestion
  timestamp — this prototype has no such timestamp to measure against; see
  `data_integrity.score_data_quality`'s docstring for the exact
  methodology.
- **Output validation's legal-compliance check is phrase-based**, not a
  semantic understanding of the question — it catches the specific
  phrasings this phase's test scenarios (and the guardrail brief's own
  examples) exercise, not every conceivable way to ask the same question.
