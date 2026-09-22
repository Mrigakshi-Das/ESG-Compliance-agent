"""Guardrail #13: confidence, from a documented methodology -- never a
bare LLM-claimed number.

Confidence is computed from five factors, each independently checkable
against signals the other guardrail modules already produced (never
against the LLM's own self-assessment):

1. Source authority     -- every regulatory source used is Tier 1 or Tier 2
2. Data integrity        -- no DATA_MISSING / DATA_CONFLICT / DATA_ANOMALY
3. Evidence completeness -- no EVIDENCE_MISSING / OUTDATED / INVALID / CONFLICT
4. Regulatory certainty  -- every regulation used is REGULATION_CURRENT
5. Calculation validation -- every calculation PASSED, none BLOCKED

HIGH requires all five met. Any critical failure (a data conflict, a
missing evidence, or a blocked calculation feeding the conclusion) caps
confidence at LOW regardless of how many other factors are fine, since
those are the failures serious enough that a reader must not treat the
conclusion as reliable. Anything else with at least one unmet factor is
MEDIUM.
"""

from __future__ import annotations

from app.guardrails.schemas import (
    ConfidenceAssessment,
    ConfidenceFactor,
    ConfidenceLevel,
    GuardrailStatus,
    RegulatoryVersionStatus,
    SourceTier,
)

_CRITICAL_DATA = {"DATA_CONFLICT", "DATA_MISSING"}
_CRITICAL_EVIDENCE = {"EVIDENCE_MISSING", "EVIDENCE_OUTDATED", "EVIDENCE_INVALID", "EVIDENCE_CONFLICT"}

METHODOLOGY = (
    "HIGH requires: authoritative source (Tier 1/2) + verified data + complete evidence "
    "+ current regulatory status + a passed deterministic calculation, all five. "
    "LOW is set whenever any factor fails in a way serious enough to make the "
    "conclusion unreliable (a data conflict, missing/outdated/conflicting evidence, or "
    "a blocked calculation). MEDIUM covers every other case with at least one unmet factor."
)


def assess_confidence(
    data_statuses: list[GuardrailStatus] | None = None,
    evidence_statuses: list[GuardrailStatus] | None = None,
    regulatory_statuses: list[RegulatoryVersionStatus] | None = None,
    calculation_statuses: list[str] | None = None,
    source_tiers: list[SourceTier] | None = None,
) -> ConfidenceAssessment:
    data_statuses = data_statuses or []
    evidence_statuses = evidence_statuses or []
    regulatory_statuses = regulatory_statuses or []
    calculation_statuses = calculation_statuses or []
    source_tiers = source_tiers or []

    source_ok = all(t in ("TIER_1_AUTHORITATIVE", "TIER_2_ORGANIZATION") for t in source_tiers) if source_tiers else True
    data_ok = all(s == "DATA_OK" for s in data_statuses) if data_statuses else True
    evidence_ok = all(s == "EVIDENCE_VERIFIED" for s in evidence_statuses) if evidence_statuses else True
    regulatory_ok = all(s == "CURRENT" for s in regulatory_statuses) if regulatory_statuses else True
    calculation_ok = all(s == "PASSED" for s in calculation_statuses) if calculation_statuses else True

    factors = [
        ConfidenceFactor("Source authority", source_ok, f"Source tiers: {source_tiers or 'none consulted'}"),
        ConfidenceFactor("Data integrity", data_ok, f"Data statuses: {data_statuses or 'none checked'}"),
        ConfidenceFactor("Evidence completeness", evidence_ok, f"Evidence statuses: {evidence_statuses or 'none checked'}"),
        ConfidenceFactor("Regulatory certainty", regulatory_ok, f"Regulatory statuses: {regulatory_statuses or 'none checked'}"),
        ConfidenceFactor("Calculation validation", calculation_ok, f"Calculation statuses: {calculation_statuses or 'none performed'}"),
    ]

    has_critical_failure = (
        any(s in _CRITICAL_DATA for s in data_statuses)
        or any(s in _CRITICAL_EVIDENCE for s in evidence_statuses)
        or any(s == "BLOCKED" for s in calculation_statuses)
    )

    if all(f.met for f in factors):
        level: ConfidenceLevel = "HIGH"
    elif has_critical_failure:
        level = "LOW"
    else:
        level = "MEDIUM"

    return ConfidenceAssessment(
        level=level,
        factors=factors,
        methodology=METHODOLOGY,
        human_review_recommended=level == "LOW",
    )
