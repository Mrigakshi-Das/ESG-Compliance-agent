"""Category-weighted readiness scoring for the management report.

Distinct from `app.calculations.scoring.calculate_overall_readiness_score`
(a flat average of every KB requirement's status weight, with no notion of
subject matter). This module answers the report-specific question Phase 7
asks for: "weight Carbon, Energy, Evidence, and Data Quality however
management cares to, and show the working" -- so the two coexist rather
than one replacing the other; the report shows both.

Every category score is built from the *same* per-status weights
(`readiness_weight_for_status`) already used and tested in Phase 6 --
this module only decides which requirements/signals belong to which
category and how to phrase the reason, never invents a new scoring scale.
"""

from dataclasses import dataclass

from app.calculations.scoring import CalculationError, readiness_weight_for_status
from app.compliance.engine import ComplianceAssessment
from app.compliance.types import Gap

DEFAULT_CATEGORY_WEIGHTS: dict[str, float] = {
    "Carbon": 0.30,
    "Energy": 0.25,
    "Evidence": 0.25,
    "Data Quality": 0.20,
}

_CARBON_REQUIREMENT_IDS = ("BEE-CCTS-001", "BEE-CCTS-002", "BEE-CCTS-003")
_ENERGY_REQUIREMENT_IDS = ("BEE-PAT-001", "BEE-PAT-002", "BEE-PAT-003")

_EVIDENCE_STATUS_SCORE: dict[str, int] = {
    "Missing": 30,
    "Outdated": 40,
    "Conflicting": 20,
    "Mixed": 60,
}

_DATA_QUALITY_OVERALL_SCORE: dict[str, int] = {
    "Clean": 100,
    "Issues Flagged": 70,
    "Missing Data": 40,
    "Conflicts Found": 20,
}


@dataclass
class CategoryScore:
    category: str
    weight: float
    score: float
    reason: str


def _gap_for_metric(gaps: list[Gap], metric: str) -> Gap | None:
    return next((g for g in gaps if g.metric == metric), None)


def _carbon_category_score(assessment: ComplianceAssessment) -> CategoryScore:
    statuses = {rid: assessment.requirement_statuses[rid] for rid in _CARBON_REQUIREMENT_IDS if rid in assessment.requirement_statuses}
    op_gap = _gap_for_metric(assessment.gaps, "emission_intensity_tco2e_per_t_cement")

    weights = [readiness_weight_for_status(s) for s in statuses.values()]
    if op_gap:
        weights.append(readiness_weight_for_status(op_gap.status))
    score = sum(weights) / len(weights) if weights else 100.0

    parts = [f"{rid}={status}" for rid, status in statuses.items()]
    reason = f"Average of BEE CCTS requirement statuses ({', '.join(parts)})" if parts else "No BEE CCTS requirements in scope"
    if op_gap:
        reason += f", and the operational emission-intensity benchmark ({op_gap.status}, {op_gap.actual_value:.4f} vs. target {op_gap.target_value})"
    reason += "."
    return CategoryScore("Carbon", 0.0, round(score, 1), reason)


def _energy_category_score(assessment: ComplianceAssessment) -> CategoryScore:
    statuses = {rid: assessment.requirement_statuses[rid] for rid in _ENERGY_REQUIREMENT_IDS if rid in assessment.requirement_statuses}
    op_gap = _gap_for_metric(assessment.gaps, "specific_thermal_energy_consumption_gj_per_t_clinker")

    weights = [readiness_weight_for_status(s) for s in statuses.values()]
    if op_gap:
        weights.append(readiness_weight_for_status(op_gap.status))
    score = sum(weights) / len(weights) if weights else 100.0

    parts = [f"{rid}={status}" for rid, status in statuses.items()]
    reason = f"Average of BEE PAT requirement statuses ({', '.join(parts)})" if parts else "No BEE PAT requirements in scope"
    if op_gap:
        reason += f", and the operational thermal-energy benchmark ({op_gap.status}, {op_gap.actual_value:.3f} vs. target {op_gap.target_value})"
    reason += "."
    return CategoryScore("Energy", 0.0, round(score, 1), reason)


def _evidence_category_score(assessment: ComplianceAssessment) -> CategoryScore:
    total_applicable = sum(1 for s in assessment.requirement_statuses.values() if s != "Not Applicable")
    evidence_gaps = [g for g in assessment.gaps if g.evidence_status and g.evidence_status not in (None, "Compliant")]

    if total_applicable == 0:
        return CategoryScore("Evidence", 0.0, 100.0, "No applicable requirements to assess evidence for.")

    penalty = sum(100 - _EVIDENCE_STATUS_SCORE.get(g.evidence_status, 50) for g in evidence_gaps)
    score = max(0.0, 100 - penalty / total_applicable)

    if evidence_gaps:
        parts = ", ".join(f"{g.requirement_id}={g.evidence_status}" for g in evidence_gaps)
        reason = f"{len(evidence_gaps)} of {total_applicable} applicable requirement(s) have an evidence issue: {parts}."
    else:
        reason = f"All {total_applicable} applicable requirement(s) have satisfactory evidence coverage."
    return CategoryScore("Evidence", 0.0, round(score, 1), reason)


def _data_quality_category_score(assessment: ComplianceAssessment) -> CategoryScore:
    dq = assessment.data_quality
    score = _DATA_QUALITY_OVERALL_SCORE[dq.overall]

    details = []
    if dq.missing_domains:
        details.append(f"missing: {dq.missing_domains}")
    if dq.conflicting_domains:
        details.append(f"conflicting: {dq.conflicting_domains}")
    if dq.flagged_issues:
        details.append(f"{sum(len(v) for v in dq.flagged_issues.values())} issue(s) flagged in {list(dq.flagged_issues)}")
    if dq.duplicate_documents:
        details.append(f"duplicate documents: {dq.duplicate_documents}")

    reason = f"Data quality for {assessment.plant}/{assessment.period} assessed as '{dq.overall}'"
    reason += f" ({'; '.join(details)})." if details else "."
    return CategoryScore("Data Quality", 0.0, float(score), reason)


_CATEGORY_SCORERS = {
    "Carbon": _carbon_category_score,
    "Energy": _energy_category_score,
    "Evidence": _evidence_category_score,
    "Data Quality": _data_quality_category_score,
}


def calculate_weighted_readiness_score(
    assessment: ComplianceAssessment,
    weights: dict[str, float] | None = None,
) -> dict:
    """Return {"overall_score": float, "breakdown": list[CategoryScore]}.

    `weights` must be exactly the 4 configured categories (Carbon, Energy,
    Evidence, Data Quality) with fractions summing to 1.0 -- raises rather
    than silently normalizing a mistake, since a silently-renormalized
    weight set is no longer the transparent methodology this exists to
    provide.
    """
    weights = dict(weights) if weights is not None else dict(DEFAULT_CATEGORY_WEIGHTS)

    if set(weights) != set(_CATEGORY_SCORERS):
        raise CalculationError(f"weights must cover exactly {sorted(_CATEGORY_SCORERS)}, got {sorted(weights)}.")
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise CalculationError(f"Category weights must sum to 1.0, got {total}.")

    breakdown: list[CategoryScore] = []
    overall = 0.0
    for category, weight in weights.items():
        cs = _CATEGORY_SCORERS[category](assessment)
        cs.weight = weight
        overall += cs.score * weight
        breakdown.append(cs)

    return {"overall_score": round(overall, 1), "breakdown": breakdown}
