"""Tool: generate_compliance_report.

Assembles the 13-section management report from `app.compliance.engine`'s
assessment, `app.reports.scoring`'s category-weighted readiness score, and
`app.reports.kpi_dashboard`'s operational KPI snapshot. Every section's
content already exists as structured data before this module touches it --
this file only arranges it and writes the (deterministic, template-based)
executive summary; it never invents a finding, and it is never an LLM call.
"""

from dataclasses import asdict
from datetime import datetime, timezone

from app.compliance.engine import ComplianceAssessment, run_compliance_assessment
from app.compliance.requirements import get_applicable_requirements
from app.regulations.loader import load_source_registry
from app.reports.kpi_dashboard import build_kpi_dashboard
from app.reports.models import (
    COMPLIANCE_DISCLAIMER,
    ComplianceReport,
    EvidenceStatusEntry,
    HypothesisEntry,
    RootCauseSection,
    SourceCitation,
)
from app.reports.scoring import calculate_weighted_readiness_score
from app.tools.regulations import TODAY_ISO

_READINESS_BANDS: tuple[tuple[float, str], ...] = (
    (80.0, "Strong"),
    (60.0, "Adequate"),
    (40.0, "Needs Attention"),
    (0.0, "Weak"),
)


def _band_for_score(score: float) -> str:
    for threshold, label in _READINESS_BANDS:
        if score >= threshold:
            return label
    return "Weak"


def _build_executive_summary(assessment: ComplianceAssessment, score_result: dict) -> str:
    overall = score_result["overall_score"]
    band = _band_for_score(overall)
    sentences = [
        f"{assessment.plant}'s ESG readiness for {assessment.period} is {overall}/100 ({band}), "
        f"based on the configured regulatory knowledge base and this period's operating data."
    ]

    weakest = min(score_result["breakdown"], key=lambda c: c.score)
    strongest = max(score_result["breakdown"], key=lambda c: c.score)
    if weakest.category != strongest.category:
        sentences.append(f"{weakest.category} is the weakest dimension ({weakest.score:.0f}/100); {strongest.category} is the strongest ({strongest.score:.0f}/100).")

    if assessment.gaps:
        top = assessment.gaps[0]
        sentences.append(
            f"The top-priority item is {top.requirement_id} ({top.status}, priority {top.priority_band}); "
            + (f"root-cause analysis points to {top.root_cause.contributing_factors[0].lower()}." if top.root_cause and top.root_cause.contributing_factors
               else "see Priority Actions for the recommended corrective action.")
        )
    else:
        sentences.append("No compliance gaps were identified against the configured knowledge base for this period.")

    human_review_count = sum(1 for s in assessment.requirement_statuses.values() if s == "Human Review Required")
    if human_review_count:
        sentences.append(
            f"{human_review_count} requirement(s) could not be automatically classified and require human "
            "confirmation of regulatory applicability before they can be closed either way."
        )

    return " ".join(sentences)


def _root_cause_sections(assessment: ComplianceAssessment) -> list[RootCauseSection]:
    sections = []
    for gap in assessment.gaps:
        if not gap.root_cause:
            continue
        sections.append(RootCauseSection(
            requirement_id=gap.requirement_id,
            metric=gap.metric or "",
            trend=gap.root_cause.trend,
            facts=[f.statement for f in gap.root_cause.findings if f.kind == "Fact"],
            hypotheses=[
                HypothesisEntry(statement=f.statement, confidence=f.confidence)
                for f in gap.root_cause.findings if f.kind == "Hypothesis"
            ],
        ))
    return sections


def _evidence_status_entries(assessment: ComplianceAssessment) -> list[EvidenceStatusEntry]:
    return [
        EvidenceStatusEntry(
            requirement_id=g.requirement_id, regulation=g.regulation, evidence_status=g.evidence_status,
            missing_evidence=g.missing_evidence, outdated_evidence=g.outdated_evidence,
            conflicting_evidence=g.conflicting_evidence,
        )
        for g in assessment.gaps
        if g.evidence_status is not None
    ]


def _human_review_items(assessment: ComplianceAssessment) -> list[dict]:
    applicable = {a.requirement.requirement_id: a for a in get_applicable_requirements(assessment.plant)}
    items = []
    for requirement_id, status in assessment.requirement_statuses.items():
        if status != "Human Review Required":
            continue
        item = applicable.get(requirement_id)
        items.append({
            "requirement_id": requirement_id,
            "regulation": item.requirement.regulation if item else requirement_id,
            "reasons": item.applicability_reasons if item else [],
        })
    return items


def _sources_section(assessment: ComplianceAssessment) -> list[SourceCitation]:
    applicable = get_applicable_requirements(assessment.plant)
    registry = {s["source_id"]: s for s in load_source_registry()}

    cited_by: dict[str, list[str]] = {}
    for item in applicable:
        cited_by.setdefault(item.requirement.source_id, []).append(item.requirement.requirement_id)

    sources = []
    for source_id, requirement_ids in cited_by.items():
        entry = registry.get(source_id)
        if entry is None:
            continue
        sources.append(SourceCitation(
            source_id=source_id, title=entry["title"], authority=entry["authority"],
            url=entry["url"], date=entry["publication_date"], cited_by=sorted(requirement_ids),
        ))
    return sorted(sources, key=lambda s: s.source_id)


def _applicable_requirements_section(assessment: ComplianceAssessment) -> list[dict]:
    result = []
    for item in get_applicable_requirements(assessment.plant):
        r = item.requirement
        result.append({
            "requirement_id": r.requirement_id,
            "regulation": r.regulation,
            "authority": r.authority,
            "applicability_verdict": item.applicability_verdict,
            "metric": r.metric,
            "target": r.target,
            "effective_date": r.effective_date,
            "source_title": r.source_title,
            "source_url": r.source_url,
            "potentially_outdated": r.is_potentially_outdated(TODAY_ISO),
        })
    return result


def generate_compliance_report(
    plant: str,
    period: str,
    category_weights: dict[str, float] | None = None,
    assessment: ComplianceAssessment | None = None,
) -> ComplianceReport:
    """Build the full 13-section report. Pass `assessment` to reuse one
    already computed by the caller (e.g. the agent orchestrator) instead of
    recomputing it -- otherwise this runs `run_compliance_assessment`
    itself, so it also works as a standalone entry point.
    """
    assessment = assessment or run_compliance_assessment(plant, period)
    score_result = calculate_weighted_readiness_score(assessment, category_weights)

    return ComplianceReport(
        plant=plant,
        period=period,
        generated_at=datetime.now(timezone.utc).isoformat(),
        disclaimer=COMPLIANCE_DISCLAIMER,
        executive_summary=_build_executive_summary(assessment, score_result),
        readiness_score=score_result,
        kpi_dashboard=build_kpi_dashboard(plant, period),
        applicable_requirements=_applicable_requirements_section(assessment),
        compliance_status=assessment.requirement_statuses,
        key_gaps=assessment.gaps,
        root_cause_analysis=_root_cause_sections(assessment),
        priority_actions=assessment.recommendations,
        evidence_status=_evidence_status_entries(assessment),
        data_quality_issues=assessment.data_quality,
        assumptions=assessment.assumptions,
        sources=_sources_section(assessment),
        human_review_required=_human_review_items(assessment),
    )


def report_to_dict(report: ComplianceReport) -> dict:
    return asdict(report)
