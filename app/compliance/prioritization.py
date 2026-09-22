"""Turns each Gap into Risk x Business Impact x Urgency inputs and calls the
deterministic scorer (app.calculations.scoring.calculate_priority).

The scoring rules below are a fixed, documented heuristic -- not a model --
so every score is traceable back to a written rule. They are deliberately
conservative about status-driven risk (an evidence problem never scores
below a "we genuinely can't tell" baseline) and let numeric gaps scale with
how far over target the plant actually is, using compare_with_target's own
percentage_variance rather than a second guess at severity.
"""

from app.calculations.scoring import calculate_priority
from app.compliance.types import Gap

# risk, business_impact, urgency, each in [1, 5], per compliance status.
# "Potential Gap" is handled separately below since its severity scales
# with how far over target the actual value is.
_STATUS_SCORES: dict[str, tuple[float, float, float]] = {
    "Data Conflict": (4, 3, 4),      # can't trust the number at all -- high risk, needs prompt reconciliation
    "Evidence Outdated": (3, 3, 4),  # already lapsed -- urgent to renew
    "Evidence Missing": (4, 3, 3),   # can't demonstrate compliance even if the plant is fine operationally
    "Data Missing": (3, 2, 3),
    "Human Review Required": (3, 3, 2),  # applicability itself unresolved -- not yet known to be urgent
}

# Potential Gap bands by |percentage_variance| from compare_with_target.
_GAP_VARIANCE_BANDS: tuple[tuple[float, float, float, float], ...] = (
    # (variance_pct_threshold, risk, business_impact, urgency)
    (25.0, 5, 5, 4),
    (10.0, 4, 4, 3),
    (0.0, 3, 3, 3),
)


def _score_gap(gap: Gap) -> tuple[float, float, float]:
    if gap.status == "Potential Gap":
        variance_pct = abs(gap.variance_pct) if gap.variance_pct is not None else 0.0
        for threshold, risk, impact, urgency in _GAP_VARIANCE_BANDS:
            if variance_pct >= threshold:
                return risk, impact, urgency
        return _GAP_VARIANCE_BANDS[-1][1:]
    return _STATUS_SCORES.get(gap.status, (2, 2, 2))


def prioritize_gaps(gaps: list[Gap]) -> list[Gap]:
    """Annotate each gap with risk/business_impact/urgency/score/priority
    band (mutating and returning the same list), sorted highest priority
    first. "Compliant" and "Not Applicable" gaps should not be passed in --
    there is nothing to prioritize about them."""
    for gap in gaps:
        risk, business_impact, urgency = _score_gap(gap)
        result = calculate_priority(risk, business_impact, urgency)
        gap.risk, gap.business_impact, gap.urgency = risk, business_impact, urgency
        gap.priority_score, gap.priority_band = result["score"], result["priority"]

    return sorted(gaps, key=lambda g: g.priority_score, reverse=True)
