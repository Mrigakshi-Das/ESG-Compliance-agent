"""Shared state threaded through one agent run: OBSERVE -> PLAN -> ACT ->
OBSERVE -> ANALYZE -> DECIDE -> REPORT.

Holding this as one object is what makes the decision trace in
`app.agent.orchestrator` buildable as the run actually happens, and what
lets `app.reports` render a full run without re-deriving anything.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

TaskStep = Literal[
    "objective_understood",
    "plan_created",
    "tool_selected",
    "tool_called",
    "data_validated",
    "calculation_performed",
    "gap_identified",
    "root_cause_investigated",
    "priority_assigned",
    "recommendation_built",
    "report_generated",
    "guardrail_check",
]

FindingKind = Literal["Fact", "Calculation", "Assumption", "Hypothesis", "Recommendation"]

RunStatus = Literal["completed", "incomplete_missing_data", "error"]

Confidence = Literal["High", "Medium", "Low"]


@dataclass
class Objective:
    """Step 1 output: what the user actually asked for, plus any assumptions
    made to fill gaps in the request. `mentioned_plants` is separate from
    `plant` because a cross-plant comparison names several plants and has
    no single "the" plant."""

    raw_query: str
    plant: str | None
    mentioned_plants: list[str]
    reporting_period: str | None
    esg_category: str | None
    desired_output: str | None
    stated_priority: str | None
    intent: str
    assumptions: list[str] = field(default_factory=list)


@dataclass
class ActivityEntry:
    """One line of the user-facing "Agent Activity" trace -- never the raw
    chain-of-thought, only the decision-level record of what happened."""

    step: TaskStep
    description: str
    status: Literal["done", "warning", "blocked"] = "done"


@dataclass
class Finding:
    """One labeled statement in the report. The label is load-bearing: a
    reader must be able to tell a retrieved Fact from a derived Calculation
    from a filled-in Assumption from an unproven Hypothesis from an
    actionable Recommendation without reading the surrounding prose."""

    kind: FindingKind
    statement: str


@dataclass
class AgentRunState:
    objective: Objective | None = None
    requirements: list[str] = field(default_factory=list)
    plan: list[str] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    tool_results: dict[str, Any] = field(default_factory=dict)
    data_quality_flags: list[str] = field(default_factory=list)
    calculations: dict[str, Any] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    gaps: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    confidence: Confidence = "Medium"
    human_review_required: bool = False
    human_review_reasons: list[str] = field(default_factory=list)
    activity_trace: list[ActivityEntry] = field(default_factory=list)
    status: RunStatus = "completed"
    report: Any | None = None  # populated by full_assessment: an app.reports.models.ComplianceReport
    final_answer: str | None = None

    # --- Phase 12: enterprise guardrail layer (app.guardrails) -------------
    # All additive -- nothing above this line changed shape or meaning, so
    # every pre-Phase-12 caller keeps working unmodified. Populated by
    # `app.guardrails.engine.GuardrailEngine` via `_apply_guardrails` in
    # app.agent.orchestrator; see app/guardrails/__init__.py for the full
    # architecture these fields come from.
    data_sources: list[str] = field(default_factory=list)
    regulatory_sources: list[str] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    data_quality: dict[str, Any] | None = None
    confidence_assessment: dict[str, Any] | None = None
    guardrail_events: list[dict[str, Any]] = field(default_factory=list)
    pending_actions: list[dict[str, Any]] = field(default_factory=list)
    approval_required: bool = False
