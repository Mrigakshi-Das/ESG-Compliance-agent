"""Top-level agent loop: OBSERVE -> PLAN -> ACT -> OBSERVE -> ANALYZE ->
DECIDE -> REPORT.

`run()` is the single entry point. It:

1. OBSERVE  -- `app.agent.planner.parse_objective` turns the raw query into
   a structured `Objective`, filling gaps with explicit, logged assumptions.
2. PLAN     -- `app.agent.planner.build_plan` classifies the objective into
   an intent and declares the tool sequence that intent needs.
3. ACT      -- an intent-specific handler below calls exactly those tools,
   through `app.tools.registry.TOOL_REGISTRY` (never touching `app.data`
   directly), via `_call_tool`.
4. OBSERVE  -- `_call_tool` inspects each result's own status/issues
   (produced by the Phase 3 tool layer) and records data-quality flags.
5. ANALYZE  -- calculation tools run only when their inputs came back
   clean; a missing/conflicting input is recorded as an unresolved
   question, never papered over with a guessed number.
6. DECIDE   -- `_finalize` sets confidence, human-review flags, and the
   overall run status from what actually happened.
7. REPORT   -- the populated `AgentRunState` (including the decision-level
   `activity_trace`, never raw model reasoning) is returned for
   `app.reports` / the UI to render.

An LLM-driven alternative to steps 1-3 exists in `app.agent.llm_client` and
is used automatically when `ANTHROPIC_API_KEY` is configured; otherwise (the
case in this environment, and for every test and demonstration in this
phase) this deterministic planner runs, which needs no network access.
"""

from __future__ import annotations

from typing import Any, Callable

from dataclasses import asdict

from app.agent import llm_client
from app.agent.planner import build_plan, detect_domains, infer_metric_key, parse_objective
from app.agent.state import ActivityEntry, AgentRunState, Finding, Objective
from app.calculations.errors import CalculationError
from app.compliance.engine import REQUIREMENT_EVIDENCE_TYPES, run_compliance_assessment
from app.compliance.gap_analysis import investigate_root_cause
from app.data.constants import PLANTS
from app.guardrails.engine import GuardrailEngine
from app.regulations.repository import get_by_id as get_regulatory_requirement_by_id
from app.reports.report_generator import generate_compliance_report
from app.tools.errors import ToolInputError
from app.tools.regulations import TODAY_ISO
from app.tools.registry import TOOL_REGISTRY

MISSING_DATA_MESSAGE = "Unable to complete assessment because required data is missing."


def run(raw_query: str, plant_hint: str | None = None, period_hint: str | None = None) -> AgentRunState:
    state = AgentRunState()
    # Phase 12: one GuardrailEngine per run, attached to `state` as a plain
    # runtime attribute (not a dataclass field -- it isn't JSON-serializable
    # and nothing should try to include it in a report or API response
    # directly). `_call_tool` retrieves it from `state` so every handler
    # gets guardrail coverage for free without changing its own signature;
    # see app/guardrails/__init__.py for the full architecture.
    guardrails = GuardrailEngine()
    state._guardrail_engine = guardrails

    if llm_client.is_available():
        llm_client.run_agentic_loop(raw_query, state, plant_hint=plant_hint, period_hint=period_hint)
        _finalize(state, guardrails)
        return state

    # --- OBSERVE ---
    objective = parse_objective(raw_query, plant_hint, period_hint)
    state.objective = objective
    state.activity_trace.append(
        ActivityEntry("objective_understood", f"Objective identified: {objective.desired_output}")
    )
    for a in objective.assumptions:
        state.findings.append(Finding("Assumption", a))

    # --- PLAN ---
    plan_spec = build_plan(objective)
    state.plan = plan_spec.steps
    state.requirements = plan_spec.tool_names
    state.activity_trace.append(
        ActivityEntry("plan_created", f"Plan created ({plan_spec.intent}): {len(plan_spec.tool_names)} tool(s) selected")
    )

    # --- ACT / OBSERVE / ANALYZE ---
    handler = _HANDLERS.get(plan_spec.intent, _execute_generic_data_lookup)
    handler(objective, state)

    # --- DECIDE / REPORT ---
    _finalize(state, guardrails)
    return state


def render_activity_trace(state: AgentRunState) -> list[dict[str, Any]]:
    """Return the decision-level activity trace for display -- the
    project's reasoning-safety requirement (no hidden chain-of-thought)."""
    symbol = {"done": "✓", "warning": "⚠", "blocked": "✗"}
    return [
        {"symbol": symbol[e.status], "step": e.step, "description": e.description, "status": e.status}
        for e in state.activity_trace
    ]


# ---------------------------------------------------------------------------
# Tool dispatch + observation recording
# ---------------------------------------------------------------------------


def _call_tool(state: AgentRunState, tool_name: str, **kwargs: Any) -> Any | None:
    guardrails: GuardrailEngine | None = getattr(state, "_guardrail_engine", None)
    _, fn = TOOL_REGISTRY[tool_name]
    try:
        result = fn(**kwargs)
    except (ToolInputError, CalculationError) as exc:
        state.data_quality_flags.append(f"{tool_name} rejected its input: {exc}")
        state.activity_trace.append(ActivityEntry("tool_called", f"{tool_name} could not run: {exc}", status="blocked"))
        if guardrails is not None and isinstance(exc, CalculationError):
            # Guardrail #6: a deterministic calculation rejected its own
            # input (non-positive production, negative emissions, a zero
            # target, ...) -- log it as a first-class guardrail event, not
            # just a data-quality flag, since this is exactly the
            # "unsupported calculation" case guardrail #1 also names.
            guardrails.log("CALCULATION_BLOCKED", "HIGH", str(exc), "BLOCK_CALCULATION", metric=tool_name)
            state.activity_trace.append(ActivityEntry("guardrail_check", f"Guardrail: calculation blocked -- {exc}", status="blocked"))
        return None

    state.tools_called.append(tool_name)
    state.tool_results[tool_name] = result
    _observe(state, tool_name, result)

    if guardrails is not None:
        status = guardrails.check_tool_result(tool_name, result)
        if status == "DATA_CONFLICT":
            detail = guardrails.data_conflict_detail(tool_name, result) if isinstance(result, dict) else None
            if detail:
                state.conflicts.append(detail)
            state.activity_trace.append(ActivityEntry("guardrail_check", f"Guardrail: data conflict detected in {tool_name} -- not auto-resolved", status="blocked"))
        elif status == "DATA_ANOMALY":
            state.activity_trace.append(ActivityEntry("guardrail_check", f"Guardrail: anomalous or duplicated value flagged in {tool_name}", status="warning"))
        if isinstance(result, dict) and result.get("status") == "ok" and tool_name not in state.data_sources:
            state.data_sources.append(tool_name)
    return result


def _observe(state: AgentRunState, tool_name: str, result: Any) -> None:
    if not isinstance(result, dict) or "status" not in result:
        # A calculation tool (bare number or a dict with no status field,
        # e.g. compare_with_target/calculate_priority) -- success is
        # already implied by not having raised.
        state.activity_trace.append(ActivityEntry("tool_called", f"Called {tool_name}", status="done"))
        return

    status = result["status"]
    for issue in result.get("issues", []):
        state.data_quality_flags.append(f"{tool_name}: {issue}")

    if status in ("missing", "conflict"):
        state.unresolved_questions.append(
            f"{tool_name} returned status='{status}' -- required data is not cleanly available."
        )
        activity_status = "blocked" if status == "conflict" else "warning"
    elif result.get("issues"):
        activity_status = "warning"
    else:
        activity_status = "done"

    subject = result.get("plant") or result.get("topic") or result.get("metric") or ""
    label = f"Called {tool_name}" + (f" ({subject})" if subject else "") + f" -> status={status}"
    state.activity_trace.append(ActivityEntry("tool_called", label, activity_status))

    values = result.get("values")
    if status == "ok" and values:
        headline = ", ".join(f"{k}={v}" for k, v in values.items())
        state.findings.append(Finding("Fact", f"{tool_name} ({result.get('period', '')}): {headline}"))


# ---------------------------------------------------------------------------
# Intent handlers -- ACT / OBSERVE / ANALYZE for each classified intent
# ---------------------------------------------------------------------------


def _execute_single_metric_emission(objective: Objective, state: AgentRunState) -> None:
    plant, period = objective.plant, objective.reporting_period
    emissions = _call_tool(state, "get_emission_data", plant=plant, period=period)
    production = _call_tool(state, "get_production_data", plant=plant, period=period)

    if not _ok(emissions) or not _ok(production):
        state.unresolved_questions.append(
            "Cannot calculate emission intensity: production or emissions data is not cleanly available."
        )
        return

    result = _call_tool(
        state, "calculate_emission_intensity",
        emissions_tco2e=emissions["values"]["total_tco2e"],
        production_tonnes=production["values"]["cement_production_tonnes"],
    )
    if result is None:
        return
    state.calculations["emission_intensity_tco2e_per_t_cement"] = result
    statement = (
        f"{plant}'s emission intensity for {period} is {result:.4f} tCO2e per tonne cement "
        f"({emissions['values']['total_tco2e']} tCO2e / {production['values']['cement_production_tonnes']} t cement)."
    )
    state.findings.append(Finding("Calculation", statement))
    state.activity_trace.append(ActivityEntry("calculation_performed", "Calculated emission intensity"))
    state.final_answer = statement


def _execute_single_metric_energy(objective: Objective, state: AgentRunState) -> None:
    # _ENERGY_WORDS in planner.py routes "thermal", "specific energy", and
    # "electricity" queries here alongside plain "energy intensity" ones --
    # so this handler must check which of those the user actually asked
    # about instead of always reporting electrical energy intensity (a
    # thermal-energy question used to silently get an electrical answer).
    plant, period = objective.plant, objective.reporting_period
    energy = _call_tool(state, "get_energy_data", plant=plant, period=period)
    if not _ok(energy):
        state.unresolved_questions.append(f"Cannot report energy data: energy data for {plant}/{period} is not cleanly available.")
        return

    metric_key = infer_metric_key(objective.raw_query)

    if metric_key == "specific_thermal_energy_consumption_gj_per_t_clinker":
        value = energy["values"]["specific_thermal_energy_consumption_gj_per_t_clinker"]
        statement = f"{plant}'s specific thermal energy consumption for {period} is {value:.3f} GJ per tonne clinker."
        state.calculations["specific_thermal_energy_consumption_gj_per_t_clinker"] = value
        state.findings.append(Finding("Fact", statement))
        state.activity_trace.append(ActivityEntry("calculation_performed", "Retrieved specific thermal energy consumption"))
        state.final_answer = statement
        return

    if metric_key == "electricity_consumption_mwh":
        value = energy["values"]["electricity_consumption_mwh"]
        statement = f"{plant}'s electricity consumption for {period} is {value:.2f} MWh."
        state.calculations["electricity_consumption_mwh"] = value
        state.findings.append(Finding("Fact", statement))
        state.activity_trace.append(ActivityEntry("calculation_performed", "Retrieved electricity consumption"))
        state.final_answer = statement
        return

    production = _call_tool(state, "get_production_data", plant=plant, period=period)
    if not _ok(production):
        state.unresolved_questions.append(
            "Cannot calculate energy intensity: production or energy data is not cleanly available."
        )
        return

    result = _call_tool(
        state, "calculate_energy_intensity",
        energy_consumption=energy["values"]["electricity_consumption_mwh"] * 1000,
        production_tonnes=production["values"]["cement_production_tonnes"],
    )
    if result is None:
        return
    state.calculations["energy_intensity_kwh_per_t_cement"] = result
    statement = f"{plant}'s electrical energy intensity for {period} is {result:.2f} kWh per tonne cement."
    state.findings.append(Finding("Calculation", statement))
    state.activity_trace.append(ActivityEntry("calculation_performed", "Calculated energy intensity"))
    state.final_answer = statement


def _execute_single_metric_generic(domain_tool: str, label: str) -> Callable[[Objective, AgentRunState], None]:
    def handler(objective: Objective, state: AgentRunState) -> None:
        result = _call_tool(state, domain_tool, plant=objective.plant, period=objective.reporting_period)
        if not _ok(result):
            state.unresolved_questions.append(f"{label} data for {objective.plant} / {objective.reporting_period} is not cleanly available.")
            return
        state.final_answer = f"{objective.plant}'s {label} data for {objective.reporting_period}: {result['values']}."

    return handler


_execute_single_metric_water = _execute_single_metric_generic("get_water_data", "water")
_execute_single_metric_waste = _execute_single_metric_generic("get_waste_data", "waste")
_execute_single_metric_production = _execute_single_metric_generic("get_production_data", "production")


def _execute_full_assessment(objective: Objective, state: AgentRunState) -> None:
    """Delegates to the Phase 6 compliance engine
    (app.compliance.engine.run_compliance_assessment), which internally
    calls the Phase 3 tool layer directly (not through `_call_tool`) since
    it composes many tools per requirement. The full internal detail is
    preserved in `state.tool_results["run_compliance_assessment"]`; the
    activity trace and findings below summarize its outcome rather than
    replaying every internal call, the same way any higher-level operation
    would be logged.
    """
    guardrails: GuardrailEngine | None = getattr(state, "_guardrail_engine", None)
    plant, period = objective.plant, objective.reporting_period
    assessment = run_compliance_assessment(plant, period)

    state.tools_called.append("run_compliance_assessment")
    state.tool_results["run_compliance_assessment"] = assessment
    # Phase 6's flat, unweighted average across every KB requirement --
    # kept under its own key since Phase 7's category-weighted score
    # (set below, once the report is built) is the one shown as
    # "the" readiness score.
    state.calculations["kb_status_readiness_score"] = assessment.overall_readiness_score

    dq = assessment.data_quality
    state.activity_trace.append(ActivityEntry(
        "data_validated",
        f"Data quality for {plant}/{period}: {dq.overall} "
        f"(missing: {dq.missing_domains or 'none'}, conflicting: {dq.conflicting_domains or 'none'}).",
        "done" if dq.overall == "Clean" else "warning",
    ))
    if dq.missing_domains:
        state.unresolved_questions.append(f"Data quality: missing domain(s) {dq.missing_domains} for {plant}/{period}.")
    if dq.conflicting_domains:
        state.unresolved_questions.append(f"Data quality: conflicting domain(s) {dq.conflicting_domains} for {plant}/{period}.")

    if guardrails is not None:
        # Guardrails #1/#2/#8: the compliance engine computes dq internally
        # (bypassing _call_tool, hence no per-tool guardrail check already
        # ran for it) -- log the same DATA_MISSING/DATA_CONFLICT events
        # `_call_tool` would have produced, and attach the numeric quality
        # score to state for the UI's Guardrails panel.
        state.data_quality = guardrails.score_data_quality(dq).as_dict()
        for domain in dq.missing_domains:
            guardrails.log("DATA_MISSING", "HIGH", f"{domain} data is missing for {plant}/{period}.", "BLOCK_CALCULATION", metric=domain)
        for domain in dq.conflicting_domains:
            guardrails.log("DATA_CONFLICT", "HIGH", f"{domain} data conflicts across sources for {plant}/{period}.", "BLOCK_CALCULATION", metric=domain, human_review_required=True)

    for note in assessment.assumptions:
        state.findings.append(Finding("Assumption", note))
    for requirement_id, status in assessment.requirement_statuses.items():
        state.findings.append(Finding("Fact", f"{requirement_id}: {status}"))
        if guardrails is not None:
            # Guardrail #3/#4: never let a requirement's status be used
            # without checking whether the underlying regulatory record is
            # actually current, authoritative, and not superseded.
            requirement = get_regulatory_requirement_by_id(requirement_id)
            if requirement is not None:
                state.regulatory_sources.append(requirement_id)
                guardrails.check_regulatory_version(requirement, TODAY_ISO)
                guardrails.check_source_tier(requirement.authority)

    state.activity_trace.append(ActivityEntry(
        "guardrail_check",
        f"Guardrail: verified regulatory source and version status for {len(state.regulatory_sources)} applicable requirement(s).",
        "done",
    ))

    state.activity_trace.append(ActivityEntry(
        "gap_identified", f"Gap analysis: {len(assessment.gaps)} gap(s) found across {len(assessment.requirement_statuses)} applicable requirement(s).",
        "warning" if assessment.gaps else "done",
    ))

    for gap in assessment.gaps:
        if gap.root_cause:
            state.activity_trace.append(ActivityEntry("root_cause_investigated", f"Root-cause investigation run for {gap.metric} ({gap.requirement_id})."))
            for f in gap.root_cause.findings:
                state.findings.append(Finding(f.kind, f.statement))
        if guardrails is not None and gap.evidence_status is not None:
            # Guardrail #7: "no evidence != compliant" -- classify and log
            # every gap that actually carries an evidence assessment.
            ev = guardrails.check_evidence(
                f"{gap.requirement_id} evidence", {"evidence_status": gap.evidence_status},
                assessment_period=period,
            )
            state.evidence.append(ev.as_dict())

    state.gaps = [asdict(g) for g in assessment.gaps]
    state.recommendations = assessment.recommendations
    if assessment.recommendations:
        state.activity_trace.append(ActivityEntry("recommendation_built", f"Built {len(assessment.recommendations)} corrective-action recommendation(s), prioritized."))

    report = generate_compliance_report(plant, period, assessment=assessment)
    state.report = report
    state.calculations["overall_readiness_score"] = report.readiness_score["overall_score"]
    state.tools_called.append("generate_compliance_report")
    state.activity_trace.append(ActivityEntry("report_generated", "Assembled the 13-section management report."))

    summary = f"ESG compliance readiness assessment for {plant} ({period}): overall readiness score {report.readiness_score['overall_score']}/100."
    top = assessment.recommendations[0] if assessment.recommendations else None
    if top:
        summary += f" Top priority ({top['priority']}): {top['gap']} -- {top['corrective_action']}"
    state.final_answer = summary


def _execute_root_cause_investigation(objective: Objective, state: AgentRunState) -> None:
    """Delegates to app.compliance.gap_analysis.investigate_root_cause,
    which walks the production -> electricity -> thermal energy -> fuel ->
    maintenance chain (see that module). As with full_assessment, the
    investigation's own internal tool calls are not individually replayed
    into `tools_called`; the full investigation object is kept in
    `tool_results["investigate_root_cause"]`.
    """
    plant = objective.plant
    metric = infer_metric_key(objective.raw_query)

    investigation = investigate_root_cause(plant, metric)
    state.tools_called.append("investigate_root_cause")
    state.tool_results["investigate_root_cause"] = investigation

    for f in investigation.findings:
        state.findings.append(Finding(f.kind, f.statement))
    state.activity_trace.append(ActivityEntry(
        "root_cause_investigated",
        f"Root-cause investigation for {plant}'s {metric}: trend={investigation.trend}, "
        f"{len(investigation.contributing_factors)} contributing factor(s) identified.",
        "warning" if investigation.trend == "increasing" else "done",
    ))

    if investigation.trend == "insufficient_data":
        state.unresolved_questions.append(f"Not enough usable historical data to establish a trend for {metric} at {plant}.")
        return

    if investigation.trend in ("flat", "decreasing"):
        state.final_answer = investigation.findings[0].statement
        return

    # Join every hypothesis rather than picking one -- a maintenance-linked
    # cause and a production-volume confound are both partial explanations,
    # not competing answers, and the reader should see all of them.
    hypotheses = [f.statement for f in investigation.findings if f.kind == "Hypothesis"]
    state.final_answer = " ".join(hypotheses) if hypotheses else investigation.findings[0].statement
    if not investigation.contributing_factors:
        state.unresolved_questions.append(f"Root cause of the rising {metric} at {plant} could not be attributed to a specific maintenance event.")


def _execute_cross_plant_comparison(objective: Objective, state: AgentRunState) -> None:
    metric = infer_metric_key(objective.raw_query)
    plants = objective.mentioned_plants if len(objective.mentioned_plants) >= 2 else PLANTS
    result = _call_tool(state, "compare_plants", metric=metric, period=objective.reporting_period, plants=plants)
    if result is None:
        return
    if result["ranked"]:
        state.findings.append(Finding("Fact", f"Ranking on {metric} for {objective.reporting_period} (best first): {', '.join(result['ranked'])}."))
        state.final_answer = f"On {metric} for {objective.reporting_period}, ranked best to worst: {', '.join(result['ranked'])}."
    if result["unavailable_plants"]:
        state.unresolved_questions.append(f"No usable {metric} data for: {', '.join(result['unavailable_plants'])}.")
        if not result["ranked"]:
            state.final_answer = None


def _execute_evidence_audit(objective: Objective, state: AgentRunState) -> None:
    plant = objective.plant
    matched_regs: dict[str, dict] = {}
    for topic in ("cement", "BRSR"):
        reg_result = _call_tool(state, "search_regulations", topic=topic)
        if reg_result:
            for r in reg_result["regulations"]:
                matched_regs[r["requirement_id"]] = r

    documents = _call_tool(state, "search_documents", plant=plant)
    # Bug fix: this used to build required_types straight from the KB's
    # long, human-readable required_evidence text (e.g. "GHG Verification
    # Statement / accredited carbon verification agency report"), which can
    # never substring-match a document's short document_type value -- every
    # audit reported "Missing" regardless of what was actually on file.
    # REQUIREMENT_EVIDENCE_TYPES is the same short-label mapping
    # app.compliance.engine uses for exactly this reason.
    required_types = sorted({
        t for rid in matched_regs for t in REQUIREMENT_EVIDENCE_TYPES.get(rid, [])
    })
    if not documents or not required_types:
        state.unresolved_questions.append("Could not determine required evidence types or retrieve documents.")
        return

    evidence_result = _call_tool(
        state, "assess_evidence",
        requirement={"required_document_types": required_types},
        available_documents=documents.get("documents", []),
    )
    if evidence_result is None:
        return
    status = evidence_result["evidence_status"]
    state.findings.append(Finding("Fact", f"{plant} evidence coverage across {len(required_types)} required document type(s): {status}."))
    if status != "Compliant":
        state.gaps.append({"category": "evidence", "status": status, **{k: v for k, v in evidence_result.items() if k != "evidence_status"}})
        state.recommendations.append({
            "gap": f"Evidence coverage is {status}",
            "suggested_action": "Close the missing/outdated/conflicting evidence items before the next audit.",
        })

    guardrails: GuardrailEngine | None = getattr(state, "_guardrail_engine", None)
    if guardrails is not None:
        # Guardrail #7: route the raw evidence_status through the same
        # "no evidence != compliant" enforcement full_assessment uses, so a
        # bare evidence_audit query gets the identical safe wording (TEST 4).
        from app.guardrails.evidence_validation import safe_evidence_statement

        ev = guardrails.check_evidence(f"{plant} evidence audit", evidence_result, assessment_period=objective.reporting_period)
        state.evidence.append(ev.as_dict())
        state.final_answer = safe_evidence_statement(ev, f"{plant}'s evidence/documentation readiness")
    else:
        state.final_answer = f"{plant}'s evidence/documentation readiness: {status}."


def _execute_regulatory_lookup(objective: Objective, state: AgentRunState) -> None:
    lower = objective.raw_query.lower()
    if "brsr" in lower:
        topic = "BRSR"
    elif "pat" in lower:
        topic = "PAT"
    elif "ccts" in lower:
        topic = "CCTS"
    else:
        domains = detect_domains(lower)
        topic = domains[0] if domains else "cement"

    result = _call_tool(state, "search_regulations", topic=topic)
    if not result or result["status"] == "no_matches":
        state.unresolved_questions.append(f"No configured regulatory requirement matched topic '{topic}'.")
        state.final_answer = None
        return
    for r in result["regulations"]:
        state.findings.append(Finding("Fact", f"{r['requirement_id']} ({r['regulation']}): {r['requirement_description']}"))
    state.final_answer = (
        f"Found {len(result['regulations'])} applicable requirement(s) for '{topic}'. {result['notice']}"
    )


def _execute_external_action_request(objective: Objective, state: AgentRunState) -> None:
    """Guardrail #10: the agent's response to any request the planner
    classified as `external_action_request` (a consequential/external
    action -- submitting a regulatory filing, sending an escalation email,
    changing plant operating parameters, modifying source data, approving
    a financial commitment, ...). Deliberately calls no data/calculation
    tool at all: the only thing this handler is allowed to do is classify
    the action's level and, for a Level 3 action, refuse to execute it and
    explain why -- never attempt it, and never silently do nothing without
    explanation (which would look, to the user, indistinguishable from a
    successfully completed action)."""
    guardrails: GuardrailEngine | None = getattr(state, "_guardrail_engine", None)
    if guardrails is None:
        guardrails = GuardrailEngine()
        state._guardrail_engine = guardrails

    action = guardrails.check_action(objective.raw_query)
    state.activity_trace.append(ActivityEntry(
        "guardrail_check",
        f"Guardrail: classified requested action as {action.level} -- "
        + ("requires human approval before it can proceed." if action.requires_approval else "may run automatically."),
        "blocked" if action.requires_approval else "done",
    ))

    if action.requires_approval:
        state.final_answer = (
            f"This request ({objective.raw_query!r}) is a Level 3 consequential action and requires explicit "
            "human authorization before it can proceed. The agent has not executed it, submitted anything, or "
            "modified any source data or system. Please have an authorized reviewer approve this action through "
            "the appropriate channel before it is carried out."
        )
        state.unresolved_questions.append(f"Action requires approval: {objective.raw_query}")
    else:
        state.final_answer = (
            f"This request ({objective.raw_query!r}) does not require external execution and can be treated as "
            f"an informational/recommendation-level request ({action.level})."
        )


def _execute_generic_data_lookup(objective: Objective, state: AgentRunState) -> None:
    plan_spec = build_plan(objective)
    any_ok = False
    for tool_name in plan_spec.tool_names:
        result = _call_tool(state, tool_name, plant=objective.plant, period=objective.reporting_period)
        if _ok(result):
            any_ok = True
    if any_ok:
        state.final_answer = f"Retrieved the requested data for {objective.plant} ({objective.reporting_period})."
    else:
        state.unresolved_questions.append("The requested data could not be cleanly retrieved.")


_HANDLERS: dict[str, Callable[[Objective, AgentRunState], None]] = {
    "single_metric_emission": _execute_single_metric_emission,
    "single_metric_energy": _execute_single_metric_energy,
    "single_metric_water": _execute_single_metric_water,
    "single_metric_waste": _execute_single_metric_waste,
    "single_metric_production": _execute_single_metric_production,
    "full_assessment": _execute_full_assessment,
    "root_cause_investigation": _execute_root_cause_investigation,
    "cross_plant_comparison": _execute_cross_plant_comparison,
    "evidence_audit": _execute_evidence_audit,
    "regulatory_lookup": _execute_regulatory_lookup,
    "generic_data_lookup": _execute_generic_data_lookup,
    "external_action_request": _execute_external_action_request,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok(result: Any) -> bool:
    return isinstance(result, dict) and result.get("status") == "ok"


def _finalize(state: AgentRunState, guardrails: GuardrailEngine | None = None) -> None:
    if state.final_answer is None:
        state.status = "incomplete_missing_data"
        state.final_answer = MISSING_DATA_MESSAGE
        state.confidence = "Low"
    elif state.data_quality_flags or state.unresolved_questions or state.gaps:
        state.status = "completed"
        state.confidence = "Medium"
    else:
        state.status = "completed"
        state.confidence = "High"

    # Gaps can come from two vocabularies: app.tools.evidence's own
    # evidence_status values ("Missing"/"Outdated"/"Conflicting"/"Mixed",
    # used by the simpler evidence_audit intent) and
    # app.calculations.scoring.ComplianceStatus ("Evidence Missing"/
    # "Evidence Outdated"/"Data Conflict"/"Human Review Required", used by
    # the full compliance engine). Both are checked rather than unified,
    # since they answer different-shaped questions upstream.
    reasons = []
    conflict_statuses = {"Conflicting", "Data Conflict"}
    evidence_gap_statuses = {"Missing", "Outdated", "Mixed", "Evidence Missing", "Evidence Outdated"}
    if any(g.get("status") in conflict_statuses for g in state.gaps):
        reasons.append("Conflicting evidence or data was found.")
    if any("conflict" in f for f in state.unresolved_questions):
        reasons.append("Conflicting source data was found for a value the objective depends on.")
    if any(g.get("status") in evidence_gap_statuses for g in state.gaps):
        reasons.append("Evidence gaps were identified that require human judgment to close.")
    if any(g.get("status") == "Human Review Required" for g in state.gaps):
        reasons.append("Regulatory applicability could not be determined from available facts and requires human confirmation.")
    if state.status == "incomplete_missing_data":
        reasons.append("Required data was missing and no result could be produced without fabricating a value.")

    state.human_review_required = bool(reasons)
    state.human_review_reasons = reasons

    # --- Phase 12: guardrail layer merge -----------------------------------
    if guardrails is not None:
        from app.guardrails.output_validation import ensure_compliance_disclaimer

        raw_query = state.objective.raw_query if state.objective else ""

        # Self-correct first: a legal-compliance-phrased question gets the
        # standard qualification appended automatically, so the common case
        # never needs the stricter block-and-replace path below.
        if state.final_answer:
            state.final_answer = ensure_compliance_disclaimer(state.final_answer, raw_query)

        # Merge guardrail-driven human-review signals with the ones already
        # computed above (union, not replacement -- either source alone is
        # sufficient reason to flag review).
        for reason in guardrails.human_review_reasons:
            if reason not in state.human_review_reasons:
                state.human_review_reasons.append(reason)
        state.human_review_required = state.human_review_required or guardrails.human_review_required

        state.pending_actions = [a.as_dict() for a in guardrails.pending_actions]
        state.approval_required = guardrails.approval_required

        state.confidence_assessment = guardrails.assess_confidence().as_dict()

        # Guardrail #14: the last checkpoint before this response is
        # considered final. A failure here overrides final_answer with a
        # safe response explaining what was missing -- never silently lets
        # an unsupported claim through.
        output_check = guardrails.validate_output(raw_query, state.final_answer, state.human_review_required)
        if not output_check.passed:
            state.final_answer = output_check.safe_response
            state.human_review_required = True
            for violation in output_check.violations:
                if violation not in state.human_review_reasons:
                    state.human_review_reasons.append(violation)

        state.guardrail_events = guardrails.events_as_dicts()
        if guardrails.events:
            state.activity_trace.append(ActivityEntry(
                "guardrail_check",
                f"Guardrail: {len(guardrails.events)} event(s) recorded this run "
                f"({sum(1 for e in guardrails.events if e.severity in ('HIGH', 'CRITICAL'))} high/critical).",
                "warning" if any(e.severity in ("HIGH", "CRITICAL") for e in guardrails.events) else "done",
            ))

    trace_status = "warning" if state.status != "completed" or state.human_review_required else "done"
    state.activity_trace.append(ActivityEntry("report_generated", f"Decision: {state.final_answer}", trace_status))
    if state.human_review_required:
        state.activity_trace.append(ActivityEntry("report_generated", "Human review required", "warning"))
    if state.approval_required:
        state.activity_trace.append(ActivityEntry("guardrail_check", "Guardrail: one or more requested actions require human approval before proceeding.", "blocked"))
