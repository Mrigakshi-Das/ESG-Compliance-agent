"""Objective parsing, task planning, and dynamic tool selection.

This is the deterministic, always-available planner: it classifies the
objective into one of several intents by keyword/pattern matching, then
composes a tool plan from that intent -- never one fixed sequence for every
request. `app.agent.llm_client` provides an alternative, genuinely
LLM-driven planner used instead of this one when `ANTHROPIC_API_KEY` is
configured (see that module and `app.agent.orchestrator.run`); this module
is what runs otherwise, and what every demonstration and test in this
phase exercises directly, since it needs no network access or credentials.

The classifier is intentionally a plain decision function, not a lookup
table of whole pre-built plans: it detects which *categories* of
information the objective needs (production, energy, emissions, water,
waste, maintenance, regulations, documents, evidence, historical trend,
cross-plant comparison) and different inputs light up different
combinations of categories, which is what makes the resulting tool
sequence genuinely a function of the input rather than a fixed workflow.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.data.constants import PERIODS, PLANTS
from app.agent.state import Objective

# ---------------------------------------------------------------------------
# Step 1: OBSERVE -- understand the objective
# ---------------------------------------------------------------------------

_PLANT_PATTERN = re.compile(r"\bplant\s*([a-c])\b", re.IGNORECASE)
_PERIOD_PATTERN = re.compile(r"\bFY\s?20\d{2}-\d{2}\s*Q[1-4]\b", re.IGNORECASE)
_PRIORITY_WORDS = ("urgent", "critical", "asap", "priority", "immediately")


def _find_mentioned_plants(text: str) -> list[str]:
    found = []
    for m in _PLANT_PATTERN.finditer(text):
        name = f"Plant {m.group(1).upper()}"
        if name in PLANTS and name not in found:
            found.append(name)
    return found


def _find_period(text: str) -> str | None:
    m = _PERIOD_PATTERN.search(text)
    if not m:
        return None
    candidate = re.sub(r"\s+", " ", m.group(0)).strip()
    candidate = candidate.replace("fy", "FY").replace("Fy", "FY")
    # Normalize to the exact configured casing/format, e.g. "FY2025-26 Q4"
    for period in PERIODS:
        if period.lower().replace(" ", "") == candidate.lower().replace(" ", ""):
            return period
    return None


def parse_objective(raw_query: str, plant_hint: str | None = None, period_hint: str | None = None) -> Objective:
    text = raw_query.strip()
    lower = text.lower()
    assumptions: list[str] = []

    mentioned = _find_mentioned_plants(text)
    if plant_hint:
        plant = plant_hint
        if plant not in mentioned:
            mentioned = [plant, *mentioned]
    elif mentioned:
        plant = mentioned[0]
    else:
        plant = None

    period = period_hint or _find_period(text)
    if period is None:
        # No explicit period named -- default to the most recent configured
        # reporting period rather than guessing a value.
        period = PERIODS[-1]
        assumptions.append(
            f"No reporting period stated; assumed the most recent configured period ({period})."
        )

    intent = _classify_intent(lower, mentioned)

    if intent != "cross_plant_comparison" and plant is None:
        plant = PLANTS[0]
        assumptions.append(f"No plant named in the request; assumed {plant} (the first configured plant).")

    esg_category = _infer_category_label(lower, intent)
    desired_output = _describe_desired_output(intent, plant, mentioned)
    stated_priority = next((w for w in _PRIORITY_WORDS if w in lower), None)

    return Objective(
        raw_query=raw_query,
        plant=plant,
        mentioned_plants=mentioned or ([plant] if plant else []),
        reporting_period=period,
        esg_category=esg_category,
        desired_output=desired_output,
        stated_priority=stated_priority,
        intent=intent,
        assumptions=assumptions,
    )


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

_COMPARISON_WORDS = ("compare plant", "compare the plants", "which plant", "best performing", "worst performing",
                     "benchmark", "rank the plants", "across plants", "among plants", "versus", " vs ")
_ROOT_CAUSE_WORDS = ("why did", "why has", "why is", "what caused", "root cause", "investigate", "explain the increase",
                     "explain the decrease")
_TREND_WORDS = ("increase", "increased", "rising", "risen", "decrease", "decreased", "declin", "worsen", "improve",
                "changed", "trend", "over time")
_ASSESSMENT_WORDS = ("assess", "readiness", "compliance review", "overall esg", "full assessment", "esg performance",
                     "audit the plant", "compliance status", "how compliant", "legally compliant", "is compliant",
                     "fully compliant", "in compliance")
_EVIDENCE_WORDS = ("evidence", "documentation", "missing documents", "document readiness", "audit trail")
_REGULATION_ONLY_WORDS = ("what does", "what is the requirement", "regulatory requirement", "requirement for",
                          "does bee", "does sebi", "brsr require", "pat require", "ccts require")

# Guardrail #10 (action authorization): a request phrased as one of these
# consequential/external actions must never reach a data-retrieval or
# compliance-assessment handler -- it's intercepted here, first, and routed
# to _execute_external_action_request, which returns
# ACTION_REQUIRES_APPROVAL rather than attempting (or silently ignoring)
# the action. Kept in sync with app.guardrails.action_authorization's own
# Level 3 keyword list; duplicated deliberately, not imported from there,
# since this list's job is *intent classification* (should this query even
# route to the action-request handler) while that module's job is
# *authorization* (what level is this specific action, once routed there) --
# two different questions that happen to share vocabulary.
_EXTERNAL_ACTION_WORDS = (
    "work order", "maintenance ticket", "escalation email", "escalate to",
    "operating parameter", "kiln setting", "plant setting",
    "modify the source", "modify source", "overwrite source", "correct the source data",
    "submit the regulatory report", "submit regulatory report", "submit the report to",
    "submit to the regulator", "file with the regulator", "send this to cpcb", "send this to bee", "send this to sebi",
    "approve financial", "financial expenditure", "approve expenditure", "authorize spending",
)

_EMISSION_WORDS = ("emission", "carbon", "ghg", "co2", "scope 1", "scope 1", "scope 2")
_ENERGY_WORDS = ("energy", "electricity", "power consumption", "thermal", "fuel", "specific energy", " sec ")
_WATER_WORDS = ("water",)
_WASTE_WORDS = ("waste",)
_PRODUCTION_WORDS = ("production", "clinker", "cement produced", "output")


def _classify_intent(lower: str, mentioned_plants: list[str]) -> str:
    # Checked first, unconditionally: a request for a consequential/external
    # action must never fall through to a data-retrieval or assessment
    # handler that would either silently ignore it or (worse) imply it was
    # carried out. See app.guardrails.action_authorization (guardrail #10).
    if any(w in lower for w in _EXTERNAL_ACTION_WORDS):
        return "external_action_request"

    if any(w in lower for w in _COMPARISON_WORDS) or (len(mentioned_plants) >= 2 and "compare" in lower):
        return "cross_plant_comparison"

    if any(w in lower for w in _ROOT_CAUSE_WORDS) and any(w in lower for w in _TREND_WORDS):
        return "root_cause_investigation"

    # Evidence-specific wording takes priority over generic "readiness"/
    # "assess" wording -- "evidence readiness" is the narrower evidence_audit
    # intent, not a full ESG assessment, even though both words can appear
    # in an assessment-flavored sentence.
    if any(w in lower for w in _EVIDENCE_WORDS):
        return "evidence_audit"

    if any(w in lower for w in _ASSESSMENT_WORDS):
        return "full_assessment"

    if any(w in lower for w in _REGULATION_ONLY_WORDS) and not any(f"plant {c.lower()}" in lower for c in "abc"):
        return "regulatory_lookup"

    domains = _match_domains(lower)
    if len(domains) == 1:
        return f"single_metric_{domains[0]}"

    return "generic_data_lookup"


def detect_domains(text: str) -> list[str]:
    """Public wrapper around the domain-keyword matcher, for callers (e.g.
    the orchestrator's regulatory-lookup handler) that need it outside the
    intent classifier itself."""
    return _match_domains(text.lower())


def _match_domains(lower: str) -> list[str]:
    domains = []
    if any(w in lower for w in _EMISSION_WORDS):
        domains.append("emission")
    if any(w in lower for w in _ENERGY_WORDS):
        domains.append("energy")
    if any(w in lower for w in _WATER_WORDS):
        domains.append("water")
    if any(w in lower for w in _WASTE_WORDS):
        domains.append("waste")
    if any(w in lower for w in _PRODUCTION_WORDS) and not domains:
        domains.append("production")
    return domains


def _infer_category_label(lower: str, intent: str) -> str:
    if intent == "full_assessment":
        return "esg_overall"
    if intent == "root_cause_investigation":
        return "investigation"
    if intent == "cross_plant_comparison":
        return "comparison"
    if intent == "evidence_audit":
        return "evidence"
    if intent == "regulatory_lookup":
        return "regulatory"
    if intent == "external_action_request":
        return "action"
    domains = _match_domains(lower)
    return domains[0] if domains else "general"


def _describe_desired_output(intent: str, plant: str | None, mentioned_plants: list[str]) -> str:
    labels = {
        "single_metric_emission": f"Calculate {plant}'s emission intensity",
        "single_metric_energy": f"Calculate {plant}'s energy intensity",
        "single_metric_water": f"Report {plant}'s water metrics",
        "single_metric_waste": f"Report {plant}'s waste metrics",
        "single_metric_production": f"Report {plant}'s production data",
        "full_assessment": f"Assess {plant}'s ESG compliance readiness",
        "root_cause_investigation": f"Investigate the cause of a metric change at {plant}",
        "cross_plant_comparison": f"Compare plants ({', '.join(mentioned_plants) or 'all configured plants'})",
        "evidence_audit": f"Audit {plant}'s evidence/documentation readiness",
        "regulatory_lookup": "Look up applicable regulatory requirements",
        "generic_data_lookup": f"Retrieve requested data for {plant}",
        "external_action_request": "Evaluate whether the requested action can be authorized",
    }
    return labels.get(intent, f"Answer the request for {plant}")


# ---------------------------------------------------------------------------
# Steps 2-3: PLAN + tool selection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanSpec:
    intent: str
    steps: list[str]
    tool_names: list[str]


def build_plan(objective: Objective) -> PlanSpec:
    """The single source of truth for both `plan_tasks` and `select_tools`
    below, and for what `app.agent.orchestrator.run` actually executes --
    keeping the declared plan and the executed plan from silently diverging.
    """
    intent = objective.intent
    plant = objective.plant

    if intent == "external_action_request":
        # Deliberately no tool calls -- guardrail #10 (action authorization)
        # requires this to stop at classification, never retrieve data or
        # attempt the action itself. See
        # app.agent.orchestrator._execute_external_action_request.
        return PlanSpec(
            intent,
            steps=["Classify the requested action's authorization level.", "Check whether it requires human approval."],
            tool_names=[],
        )

    if intent == "regulatory_lookup":
        return PlanSpec(
            intent,
            steps=["Search the regulatory knowledge base for the requested topic."],
            tool_names=["search_regulations"],
        )

    if intent == "cross_plant_comparison":
        return PlanSpec(
            intent,
            steps=[
                "Identify the metric and plants to compare.",
                "Retrieve and rank that metric across the selected plants for the reporting period.",
            ],
            tool_names=["compare_plants"],
        )

    if intent == "root_cause_investigation":
        return PlanSpec(
            intent,
            steps=[
                f"Retrieve {plant}'s historical trend for the metric in question.",
                "Walk the production -> electricity -> thermal energy -> fuel driver chain for a notable co-occurring change.",
                f"Retrieve {plant}'s maintenance and calibration history for corroborating context.",
                "Correlate the trend with drivers and maintenance events to form a hypothesis (not a certainty).",
            ],
            tool_names=["investigate_root_cause"],
        )

    if intent == "full_assessment":
        return PlanSpec(
            intent,
            steps=[
                "Identify applicable carbon, energy, and disclosure requirements.",
                f"Retrieve {plant}'s production, emissions, and energy data.",
                f"Search {plant}'s evidence/document repository.",
                "Calculate emission intensity and energy intensity.",
                "Assess evidence coverage against the required document types.",
                "Compare calculated intensity against the configured target, where one is available.",
            ],
            tool_names=[
                "search_regulations", "get_production_data", "get_emission_data", "get_energy_data",
                "search_documents", "calculate_emission_intensity", "calculate_energy_intensity",
                "assess_evidence", "compare_with_target",
            ],
        )

    if intent == "evidence_audit":
        return PlanSpec(
            intent,
            steps=[
                "Identify which evidence types the applicable requirements call for.",
                f"Search {plant}'s document repository.",
                "Assess evidence coverage against the required document types.",
            ],
            tool_names=["search_regulations", "search_documents", "assess_evidence"],
        )

    if intent == "single_metric_emission":
        return PlanSpec(
            intent,
            steps=[f"Retrieve {plant}'s emissions and production data.", "Calculate emission intensity."],
            tool_names=["get_emission_data", "get_production_data", "calculate_emission_intensity"],
        )

    if intent == "single_metric_energy":
        return PlanSpec(
            intent,
            steps=[f"Retrieve {plant}'s energy and production data.", "Calculate energy intensity."],
            tool_names=["get_energy_data", "get_production_data", "calculate_energy_intensity"],
        )

    if intent == "single_metric_water":
        return PlanSpec(intent, steps=[f"Retrieve {plant}'s water data."], tool_names=["get_water_data"])

    if intent == "single_metric_waste":
        return PlanSpec(intent, steps=[f"Retrieve {plant}'s waste data."], tool_names=["get_waste_data"])

    if intent == "single_metric_production":
        return PlanSpec(intent, steps=[f"Retrieve {plant}'s production data."], tool_names=["get_production_data"])

    # generic_data_lookup: fetch whichever raw categories the text names.
    domain_tools = {
        "emission": "get_emission_data",
        "energy": "get_energy_data",
        "water": "get_water_data",
        "waste": "get_waste_data",
        "production": "get_production_data",
    }
    domains = _match_domains(objective.raw_query.lower()) or ["production"]
    tools = [domain_tools[d] for d in domains]
    return PlanSpec(
        intent,
        steps=[f"Retrieve {plant}'s {', '.join(domains)} data."],
        tool_names=tools,
    )


_METRIC_KEYWORD_MAP: tuple[tuple[tuple[str, ...], str], ...] = (
    (("carbon intensity", "emission intensity"), "emission_intensity_tco2e_per_t_cement"),
    (("scope 1",), "scope_1_tco2e"),
    (("scope 2",), "scope_2_tco2e"),
    (("total emission", "ghg emission", "carbon emission"), "total_tco2e"),
    (("energy intensity",), "energy_intensity_kwh_per_t_cement"),
    (("thermal energy", "specific thermal"), "specific_thermal_energy_consumption_gj_per_t_clinker"),
    (("electricity", "power consumption"), "electricity_consumption_mwh"),
    (("water intensity", "water"), "water_intensity_m3_per_t_cement"),
    (("waste",), "waste_generated_tonnes"),
    (("clinker",), "clinker_production_tonnes"),
    (("cement production", "cement produced"), "cement_production_tonnes"),
)

_DEFAULT_METRIC = "emission_intensity_tco2e_per_t_cement"


def infer_metric_key(text: str) -> str:
    """Map free text to one of `app.tools.metrics.METRIC_REGISTRY`'s keys.
    Falls back to emission intensity -- the most common "how is this plant
    doing" proxy -- when nothing more specific is named, rather than
    refusing to answer.
    """
    lower = text.lower()
    for keywords, metric in _METRIC_KEYWORD_MAP:
        if any(k in lower for k in keywords):
            return metric
    return _DEFAULT_METRIC


def plan_tasks(objective: Objective) -> list[str]:
    """Return an ordered list of task descriptions, sized to the objective."""
    return build_plan(objective).steps


def select_tools(objective: Objective, plan: list[str] | None = None) -> list[str]:
    """Return the tool names actually required for this objective -- never
    all tools by default. `plan` is accepted for interface compatibility
    with callers that already have `plan_tasks`'s output; it is not needed
    to compute the answer since `build_plan` is the single source of truth.
    """
    return build_plan(objective).tool_names
