"""Flask API for the control-tower UI. Thin by design: every route either
returns static configuration (plants/periods) or calls
`app.agent.orchestrator.run` and serializes the resulting `AgentRunState` --
no business logic lives here. The static frontend in `app/ui/static/`
renders whatever this returns.
"""

from __future__ import annotations

import io
from dataclasses import asdict
from typing import Any

from flask import Flask, Response, jsonify, request, send_from_directory

from app.agent.orchestrator import render_activity_trace, run
from app.data.constants import PERIODS, PLANTS
from app.reports.renderers import render_pdf

app = Flask(__name__, static_folder="static", static_url_path="")

ASSESSMENT_TYPES: list[dict[str, str]] = [
    {"id": "full_assessment", "label": "Full ESG Assessment", "template": "Assess {plant}'s ESG compliance readiness."},
    {"id": "emission_intensity", "label": "Emission Intensity", "template": "Calculate {plant}'s emission intensity."},
    {"id": "energy_intensity", "label": "Energy Intensity", "template": "Calculate {plant}'s energy intensity."},
    {"id": "root_cause", "label": "Root-Cause Investigation", "template": "Why did {plant}'s carbon intensity increase?"},
    {"id": "evidence_audit", "label": "Evidence Audit", "template": "Audit {plant}'s evidence readiness."},
    {"id": "compare_plants", "label": "Compare All Plants", "template": "Compare plants on emission intensity for {period}."},
]

EXAMPLE_QUERIES = [
    "Why did Plant B's carbon intensity increase?",
    "Assess Plant A's ESG compliance readiness.",
    "What is Plant C's water intensity?",
    "Compare plants on emission intensity for FY2025-26 Q4.",
    "What does BRSR Core require?",
]


@app.get("/")
def index() -> Response:
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/config")
def config() -> Response:
    return jsonify({
        "plants": PLANTS,
        "periods": PERIODS,
        "default_period": PERIODS[-1],
        "assessment_types": ASSESSMENT_TYPES,
        "example_queries": EXAMPLE_QUERIES,
    })


@app.post("/api/run")
def run_assessment() -> Response:
    body = request.get_json(silent=True) or {}
    query = (body.get("query") or "").strip()
    plant = body.get("plant") or None
    period = body.get("period") or None
    assessment_type = body.get("assessment_type") or "full_assessment"

    if not query:
        template = next((t["template"] for t in ASSESSMENT_TYPES if t["id"] == assessment_type), ASSESSMENT_TYPES[0]["template"])
        query = template.format(plant=plant or PLANTS[0], period=period or PERIODS[-1])

    try:
        state = run(query, plant_hint=plant, period_hint=period)
    except Exception as exc:  # a genuine bug, not an agent-level "incomplete" outcome
        return jsonify({"error": True, "message": f"The agent service failed unexpectedly: {exc}"}), 500

    return jsonify(_serialize_state(state))


@app.get("/api/report.pdf")
def report_pdf() -> Response:
    plant = request.args.get("plant", PLANTS[0])
    period = request.args.get("period", PERIODS[-1])
    if plant not in PLANTS or period not in PERIODS:
        return jsonify({"error": True, "message": "Unknown plant or period."}), 400

    from app.reports.report_generator import generate_compliance_report

    try:
        report = generate_compliance_report(plant, period)
        buffer = io.BytesIO()
        render_pdf(report, buffer)
        buffer.seek(0)
    except Exception as exc:  # e.g. an fpdf2 rendering edge case -- never surface a raw traceback
        return jsonify({"error": True, "message": f"Could not generate the PDF report: {exc}"}), 500
    filename = f"{plant.replace(' ', '_')}_{period.replace(' ', '_')}_ESG_report.pdf"
    return Response(
        buffer.read(), mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _serialize_state(state) -> dict[str, Any]:
    objective = state.objective
    report = state.report

    return {
        "objective": {
            "raw_query": objective.raw_query,
            "plant": objective.plant,
            "mentioned_plants": objective.mentioned_plants,
            "reporting_period": objective.reporting_period,
            "intent": objective.intent,
            "desired_output": objective.desired_output,
            "assumptions": objective.assumptions,
        } if objective else None,
        "status": state.status,
        "confidence": state.confidence,
        "human_review_required": state.human_review_required,
        "human_review_reasons": state.human_review_reasons,
        "final_answer": state.final_answer,
        "activity_trace": render_activity_trace(state),
        "findings": [asdict(f) for f in state.findings],
        "unresolved_questions": state.unresolved_questions,
        "data_quality_flags": state.data_quality_flags,
        "calculations": state.calculations,
        "has_report": report is not None,
        "readiness_score": _readiness_score_payload(report),
        "kpi_dashboard": [asdict(k) for k in report.kpi_dashboard] if report else [],
        "key_gaps": [asdict(g) for g in report.key_gaps] if report else [],
        "root_cause_analysis": [asdict(rc) for rc in report.root_cause_analysis] if report else [],
        "priority_actions": report.priority_actions if report else [],
        "evidence_status": [asdict(e) for e in report.evidence_status] if report else [],
        "data_quality_issues": asdict(report.data_quality_issues) if report else None,
        "compliance_status": report.compliance_status if report else {},
        "sources": [asdict(s) for s in report.sources] if report else [],
        "assumptions": report.assumptions if report else objective.assumptions if objective else [],
        "executive_summary": report.executive_summary if report else None,
        # Phase 12: enterprise guardrail layer -- see app/guardrails/.
        "conflicts": state.conflicts,
        "evidence": state.evidence,
        "data_quality": state.data_quality,
        "confidence_assessment": state.confidence_assessment,
        "guardrail_events": state.guardrail_events,
        "pending_actions": state.pending_actions,
        "approval_required": state.approval_required,
        "guardrails": _guardrail_dashboard(state),
    }


def _guardrail_dashboard(state) -> dict[str, Any] | None:
    engine = getattr(state, "_guardrail_engine", None)
    if engine is None:
        return None
    from app.guardrails.schemas import DataQualityScore

    dq = DataQualityScore(**{k: v for k, v in state.data_quality.items() if k != "overall"}) if state.data_quality else None
    return engine.dashboard(dq)


def _readiness_score_payload(report) -> dict[str, Any] | None:
    if report is None:
        return None
    return {
        "overall_score": report.readiness_score["overall_score"],
        "breakdown": [asdict(c) for c in report.readiness_score["breakdown"]],
    }
