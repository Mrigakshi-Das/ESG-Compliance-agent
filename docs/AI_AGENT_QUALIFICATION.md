# How This Qualifies as an AI Agent

This system is not a chatbot with an ESG-flavored prompt. A chatbot takes
text in, produces text out, and has no persistent notion of a task, a plan,
or a decision it is accountable for. Every property below is something a
chatbot architecture does not have, and every claim points at the actual
code and test that backs it — not a description of intended behavior.

## Autonomy

Given one natural-language objective, the system independently determines
*what to do* — no human specifies which tools to call or in what order.
`app.agent.orchestrator.run()` is a single entry point; everything from
objective parsing through report generation happens without further human
input. The same entry point produces qualitatively different behavior for
qualitatively different requests — a single-metric question, a full
compliance assessment, a root-cause investigation, a cross-plant comparison,
an evidence audit, or a pure regulatory lookup — each exercised as a
distinct, asserted-different tool sequence in
`app/tests/test_agent_orchestrator.py` (see the table in
[DEMO.md](DEMO.md)'s "Additional demonstrations" section).

## Planning

`app.agent.planner.parse_objective` turns raw text into a structured
`Objective`, and `build_plan` derives an intent-specific, multi-step plan
*before* any tool executes — the plan for `full_assessment` is a 6-step,
9-tool sequence; the plan for `single_metric_emission` is a 2-step, 3-tool
sequence. This is planning in the literal sense: the sequence of actions is
decided as a unit ahead of execution, not improvised call-by-call, and it is
a genuine function of the classified intent rather than one fixed script —
verified by `test_agent_planner.py`'s assertions that different objectives
produce different plans.

An optional LLM-driven planner (`app.agent.llm_client`, active only when
`ANTHROPIC_API_KEY` is set) demonstrates the same planning capability
through a real Claude tool-use loop instead of the deterministic rules —
same interface, same guarantee that the LLM decides *which* tool to call
next but never computes a value itself.

## Tool use

The agent's only way to touch data or perform a calculation is through 15
registered tools (`app/tools/registry.py`'s `TOOL_REGISTRY`) — it cannot
read `app/data` or `app/regulations` directly. Each tool call is dispatched
through `_call_tool`, which records the call, inspects the result's own
status, and reacts to what came back (a `missing` or `conflict` status
skips the dependent calculation and logs an unresolved question instead of
guessing) — this is genuine tool use with observation-driven branching, not
a fixed pipeline of function calls. The compliance engine
(`app.compliance.engine.run_compliance_assessment`) composes many of these
same tools per regulatory requirement for the broader `full_assessment`
intent, and its own internal tool-call detail is preserved rather than
collapsed away (see [architecture.md](architecture.md) §2).

## State

`app.agent.state.AgentRunState` accumulates everything the run has done —
the objective, the plan, every tool called and its raw result, calculations
performed, findings (each labeled Fact/Calculation/Assumption/Hypothesis),
gaps found, recommendations built, unresolved questions, and a running
activity trace — as the run progresses. Later stages read this accumulated
state to make decisions: gap identification reads the validated data,
root-cause investigation reads the identified gaps, recommendation-building
reads the root-cause findings, and the final report assembles from
everything gathered along the way. This is a real working memory for one
task execution, not a stateless request/response.

## Reasoning at the decision level

The system exposes *what it decided and why* without exposing an internal
chain-of-thought — `render_activity_trace(state)` returns a ✓/⚠/✗ list:
objective understood → plan created → data validated → gaps identified →
root cause investigated → recommendations built → report generated → final
decision. Each line is a decision point with a visible outcome (see
[DEMO.md](DEMO.md) for a full captured example), and the underlying findings
carry explicit reasoning labels — a `Hypothesis` about a root cause is never
presented with the same confidence as a `Fact`, and each hypothesis carries
its own High/Medium/Low confidence level. This is the brief's explicit
requirement: show the decision trace, never a hidden internal monologue.

## Feedback loop

The agent reacts to what its own tool calls return, within a single run:
if `get_production_data` comes back `missing` for a required period, the
dependent `calculate_emission_intensity` call is skipped and an unresolved
question is logged — a genuine runtime branch based on an intermediate
observation, not something baked into the upfront plan. At the compliance
level, `investigate_root_cause` is only triggered for gaps that are both
numeric and classified `Potential Gap` — the decision to investigate root
cause is itself conditioned on what gap analysis (an earlier stage) found.
`_finalize`'s confidence and `human_review_required` determination is
likewise computed from what actually happened during the run (were there
evidence gaps? was applicability unresolved?), not set upfront.

## Error handling

Every tool raises a typed error (`ToolInputError`, `CalculationError`) on
invalid input rather than returning a wrong number, and `_call_tool` catches
exactly those types, logs a data-quality flag and a blocked activity-trace
entry, and lets the run continue with that fact marked missing — a
malformed request degrades gracefully into "here's what I couldn't
determine," never a crash or a silently wrong answer. When a core
calculation cannot complete because of missing/conflicting data, the agent
returns the fixed, honest
`"Unable to complete assessment because required data is missing."` message
rather than fabricating a result — this is a defined stopping condition,
verified by `test_ui_server.py`'s missing-data scenario test end-to-end
through the API. At the UI layer, every Flask route now catches unexpected
exceptions and returns a clean JSON error rather than a raw traceback (see
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) for the one gap found and fixed
here during this phase's review).

## What would make this *not* an agent

For contrast: if `run()` simply formatted the user's question into a prompt
and returned an LLM's free-text response, none of the above would hold —
there would be no plan distinct from the answer, no tool-selection decision
to inspect, no state to accumulate across steps, and no way to distinguish
a Fact from a Hypothesis except by re-reading the prose. The architectural
choice made throughout this project — deterministic tools and calculations,
an orchestration layer that plans and dispatches, an LLM (when used at all)
confined to the planning/selection step — is what makes autonomy, planning,
state, and a real feedback loop possible to build and to test.
