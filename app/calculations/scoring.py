"""Deterministic comparison and scoring math shared across ESG domains.

`app.compliance.prioritization` (Phase 7) decides *what* risk/impact/urgency
values to feed `calculate_priority`, and what target/direction to feed
`compare_with_target` (business logic); this module only does the
arithmetic. No LLM involvement.
"""

from typing import Literal

from app.calculations.errors import CalculationError

ComplianceStatus = Literal[
    "Compliant",
    "Potential Gap",
    "Data Missing",
    "Evidence Missing",
    "Evidence Outdated",
    "Data Conflict",
    "Not Applicable",
    "Human Review Required",
]

# Fixed, documented per-status weight for calculate_overall_readiness_score.
# Compliant scores full marks; every other status reflects how much doubt
# it leaves about whether the requirement is actually being met -- not just
# "did we get a number". "Not Applicable" is excluded entirely, not scored.
_READINESS_WEIGHTS: dict[ComplianceStatus, int] = {
    "Compliant": 100,
    "Potential Gap": 40,
    "Human Review Required": 50,
    "Evidence Outdated": 40,
    "Evidence Missing": 30,
    "Data Missing": 20,
    "Data Conflict": 20,
}

PriorityLevel = Literal["Critical", "High", "Medium", "Low"]
TargetDirection = Literal["lower_is_better", "higher_is_better"]
TargetVerdict = Literal["Within Target", "Exceeds Target", "Below Target"]

# score = risk * business_impact * urgency, each factor in [1, 5] -> max 125.
_PRIORITY_BANDS: list[tuple[float, PriorityLevel]] = [
    (80.0, "Critical"),
    (40.0, "High"),
    (15.0, "Medium"),
]
_FACTOR_RANGE = (1.0, 5.0)


def compare_with_target(
    actual: float,
    target: float,
    metric: str,
    direction: TargetDirection = "lower_is_better",
) -> dict[str, float | str]:
    """Return variance, percentage variance, and a target verdict for
    `metric`.

    `direction` says which way is compliant: "lower_is_better" (a ceiling,
    e.g. emission intensity, energy intensity -- the default, since every
    numeric target in the Phase 2 dataset is a ceiling) or
    "higher_is_better" (a floor, e.g. renewable energy share).

    Raises CalculationError if `target` is zero (percentage variance is
    undefined) or if either value is not numeric -- a qualitative
    requirement (e.g. "Mandatory disclosure") cannot be compared this way
    and must be routed to human/compliance review instead of being forced
    through this function.
    """
    try:
        actual_f, target_f = float(actual), float(target)
    except (TypeError, ValueError) as exc:
        raise CalculationError(
            f"actual and target must both be numeric to compare against {metric!r}; "
            f"got actual={actual!r}, target={target!r}"
        ) from exc
    if target_f == 0:
        raise CalculationError(f"target for {metric!r} is 0 -- percentage variance is undefined")

    variance = actual_f - target_f
    percentage_variance = (variance / target_f) * 100

    if direction == "lower_is_better":
        status: TargetVerdict = "Within Target" if actual_f <= target_f else "Exceeds Target"
    elif direction == "higher_is_better":
        status = "Within Target" if actual_f >= target_f else "Below Target"
    else:
        raise CalculationError(f"Unknown direction {direction!r}; expected 'lower_is_better' or 'higher_is_better'")

    return {
        "metric": metric,
        "actual": actual_f,
        "target": target_f,
        "variance": variance,
        "percentage_variance": percentage_variance,
        "status": status,
    }


def calculate_priority(risk: float, business_impact: float, urgency: float) -> dict[str, float | str]:
    """Return {"score": risk * business_impact * urgency, "priority": <PriorityLevel>}.

    Each of risk/business_impact/urgency must be a number in [1, 5] (1 =
    lowest, 5 = highest) -- CalculationError otherwise. Score therefore
    ranges 1-125; bands (Critical >= 80, High >= 40, Medium >= 15, else Low)
    are a fixed, documented convention for this prototype.
    """
    lo, hi = _FACTOR_RANGE
    for name, value in (("risk", risk), ("business_impact", business_impact), ("urgency", urgency)):
        try:
            value_f = float(value)
        except (TypeError, ValueError) as exc:
            raise CalculationError(f"{name} must be numeric, got {value!r}") from exc
        if not (lo <= value_f <= hi):
            raise CalculationError(f"{name} must be in [{lo}, {hi}], got {value_f}")

    score = float(risk) * float(business_impact) * float(urgency)
    priority: PriorityLevel = "Low"
    for threshold, band in _PRIORITY_BANDS:
        if score >= threshold:
            priority = band
            break

    return {"score": score, "priority": priority}


def readiness_weight_for_status(status: ComplianceStatus) -> int:
    """Public accessor for a single status's readiness weight (0-100) --
    used by `app.reports.scoring` to build category-level scores from the
    same authoritative per-status weighting `calculate_overall_readiness_score`
    uses, sliced by subject-matter category instead of averaged flatly
    across every requirement.
    """
    if status not in _READINESS_WEIGHTS:
        raise CalculationError(f"Unrecognized compliance status {status!r}.")
    return _READINESS_WEIGHTS[status]


def calculate_overall_readiness_score(status_by_requirement: dict[str, ComplianceStatus]) -> int:
    """Return an overall 0-100 ESG readiness score from per-requirement
    compliance statuses, using the fixed weighting in `_READINESS_WEIGHTS`.

    "Not Applicable" requirements are excluded from the average entirely --
    they say nothing about readiness either way. A requirement with an
    unrecognized status raises rather than being silently skipped or
    zero-scored, since that would hide a real classification bug.

    Returns 100 (vacuously "fully ready") when there are no scoreable
    requirements at all -- an empty set is not a compliance failure.
    """
    scoreable = {k: v for k, v in status_by_requirement.items() if v != "Not Applicable"}
    if not scoreable:
        return 100

    total = 0
    for requirement_id, status in scoreable.items():
        if status not in _READINESS_WEIGHTS:
            raise CalculationError(f"Unrecognized compliance status {status!r} for {requirement_id!r}.")
        total += _READINESS_WEIGHTS[status]

    return round(total / len(scoreable))
