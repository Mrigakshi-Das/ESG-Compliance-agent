"""Aggregates every authority module into one queryable regulatory
knowledge base. This is what `app.tools.regulations.search_regulations`
calls -- Phase 1's architecture named this swap explicitly: same tool
signature, real sourced backend instead of the Phase 2 placeholder table.
"""

from app.regulations import bee, environmental, sebi
from app.regulations.schema import RegulatoryRequirement


def all_requirements() -> list[RegulatoryRequirement]:
    return [*bee.load_requirements(), *sebi.load_requirements(), *environmental.load_requirements()]


def get_by_id(requirement_id: str) -> RegulatoryRequirement | None:
    for r in all_requirements():
        if r.requirement_id == requirement_id:
            return r
    return None


def search(
    topic: str,
    reporting_period: str | None = None,
) -> list[RegulatoryRequirement]:
    """Case-insensitive substring match against regulation name, metric,
    and requirement description. `reporting_period` further filters to
    records whose reporting_period text mentions it.
    """
    topic_lower = topic.lower()
    matches = [
        r
        for r in all_requirements()
        if topic_lower in r.regulation.lower()
        or topic_lower in r.metric.lower()
        or topic_lower in r.requirement_description.lower()
    ]
    if reporting_period:
        matches = [r for r in matches if reporting_period in r.reporting_period]
    return matches


def flag_outdated(requirements: list[RegulatoryRequirement], as_of: str) -> list[RegulatoryRequirement]:
    """Return the subset of `requirements` whose last_reviewed date is stale
    as of `as_of` -- a single date comparison per record, never a judgment
    call. See RegulatoryRequirement.is_potentially_outdated.
    """
    return [r for r in requirements if r.is_potentially_outdated(as_of)]
