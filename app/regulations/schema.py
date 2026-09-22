"""Shared schema every regulatory record must satisfy, regardless of which
authority module (bee.py, sebi.py, environmental.py) defines it.

Two structures:

- `ApplicabilityCondition` makes "does this requirement apply here" an
  explicit, evaluable fact rather than free text -- e.g. BRSR obligations
  attach to the *listed company* (by market-cap rank), not the plant, while
  PAT/CCTS obligations attach to the *plant* (by Designated Consumer /
  Obligated Entity status). A requirement can carry several of these.
- `RegulatoryRequirement` is the full sourced record. Every field the
  Phase 4 brief asks for is here, plus `version` and
  `superseded_or_amended_by` for version control, and `confidence` /
  `status` so the KB can be honest about what it does and doesn't know for
  certain.

`is_potentially_outdated()` is a single date check (against
`last_reviewed`), not an LLM judgment -- see the module docstring in
`app/regulations/__init__.py`.
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal

ApplicabilityLevel = Literal["plant", "company"]
Confidence = Literal["High", "Medium", "Low"]
RequirementStatus = Literal["Active", "Under Amendment", "Draft/Proposed", "Superseded"]


@dataclass(frozen=True)
class ApplicabilityCondition:
    """One fact that must be known to determine whether a requirement
    applies. Deliberately does not resolve itself -- resolving it against a
    specific plant/company is `app.regulations.applicability`'s job, using
    whatever facts the caller can actually supply. When the caller can't
    supply the fact, the honest answer is "cannot determine", never a
    default guess.
    """

    level: ApplicabilityLevel
    criterion: str  # e.g. "designated_consumer_status", "obligated_entity_status", "listed_entity_market_cap_rank"
    description: str
    parameter: str | None = None  # e.g. a threshold or band this criterion is checked against


@dataclass(frozen=True)
class RegulatoryRequirement:
    requirement_id: str
    regulation: str
    authority: str
    industry: str
    requirement_description: str
    applicability: str  # human-readable summary
    applicability_conditions: tuple[ApplicabilityCondition, ...]
    metric: str
    unit: str
    target: str  # numeric targets are plant/entity-specific per source in several of these regulations -- see each record's target text and source
    reporting_period: str
    reporting_frequency: str
    required_evidence: tuple[str, ...]
    effective_date: str  # ISO date
    source_id: str  # links to an entry in app/regulations/sources/registry.json
    source_title: str
    source_url: str
    source_date: str  # ISO date of the cited notification/circular
    last_reviewed: str  # ISO date this KB record was last checked against its source
    confidence: Confidence
    status: RequirementStatus
    version: str
    superseded_or_amended_by: str | None = None
    notes: str = ""

    def is_potentially_outdated(self, as_of: str, staleness_days: int = 365) -> bool:
        """True if `last_reviewed` is more than `staleness_days` before
        `as_of` (both ISO date strings) -- a fixed date comparison, not a
        judgment call. The agent should surface this as "Potentially
        outdated regulatory information", not silently trust a stale record.
        """
        reviewed = date.fromisoformat(self.last_reviewed)
        reference = date.fromisoformat(as_of)
        return (reference - reviewed).days > staleness_days
