"""Typed vocabulary shared by every guardrail module.

Deliberately a *separate* vocabulary from `app.calculations.scoring.
ComplianceStatus` ("Compliant", "Potential Gap", "Data Missing", ...) --
that status describes one regulatory requirement's compliance-readiness
verdict, a concept that already exists and is extensively tested. This
module's `GuardrailStatus` describes the guardrail *engine's own signals*
(did this tool call return clean data? was a conflict detected? is human
review required?) -- a different, additive layer, not a replacement. The
two vocabularies overlap in meaning at points (a "conflict" tool status
and a `DATA_CONFLICT` guardrail status describe the same underlying fact)
and the mapping is intentional, but nothing here renames or repurposes the
existing `ComplianceStatus` strings anywhere they are already used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Status vocabularies
# ---------------------------------------------------------------------------

GuardrailStatus = Literal[
    "DATA_OK",
    "DATA_MISSING",
    "DATA_CONFLICT",
    "DATA_ANOMALY",
    "EVIDENCE_VERIFIED",
    "EVIDENCE_MISSING",
    "EVIDENCE_OUTDATED",
    "EVIDENCE_INVALID",
    "EVIDENCE_CONFLICT",
    "REGULATION_CURRENT",
    "REGULATION_OUTDATED",
    "REGULATION_FUTURE_EFFECTIVE",
    "REGULATION_UNCERTAIN",
    "HUMAN_REVIEW_REQUIRED",
    "ACTION_REQUIRES_APPROVAL",
    "CALCULATION_PASSED",
    "CALCULATION_BLOCKED",
]

RegulatoryVersionStatus = Literal[
    "CURRENT", "OUTDATED", "FUTURE_EFFECTIVE", "UNKNOWN",
]

SourceTier = Literal["TIER_1_AUTHORITATIVE", "TIER_2_ORGANIZATION", "TIER_3_SECONDARY"]

ConfidenceLevel = Literal["HIGH", "MEDIUM", "LOW"]

ActionLevel = Literal["LEVEL_1_INFORMATIONAL", "LEVEL_2_RECOMMENDATION", "LEVEL_3_CONSEQUENTIAL"]

Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


# ---------------------------------------------------------------------------
# Provenance -- every important value's origin
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Provenance:
    """Where one factual value came from. Attached to a value, never
    inferred after the fact -- `data_integrity.tag_provenance` builds this
    directly from the tool call that produced the value, so there is no
    window where a number exists without a traceable origin."""

    source: str  # e.g. "get_production_data", "search_regulations", "assess_evidence"
    source_type: Literal["registered_tool", "validated_document", "approved_regulatory_source", "prior_verified_state"]
    period: str | None = None
    plant: str | None = None
    verified: bool = True
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_type": self.source_type,
            "period": self.period,
            "plant": self.plant,
            "verified": self.verified,
            "retrieved_at": self.retrieved_at,
        }


@dataclass(frozen=True)
class ProvenancedValue:
    """A value plus its Provenance -- the shape guardrail #1 asks for
    (`{value, unit, source, period, verified}`), generalized to any field
    name via `as_dict()`."""

    value: Any
    unit: str
    provenance: Provenance

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "unit": self.unit,
            "source": self.provenance.source,
            "period": self.provenance.period,
            "verified": self.provenance.verified,
        }


# ---------------------------------------------------------------------------
# Guardrail event log
# ---------------------------------------------------------------------------


@dataclass
class GuardrailEvent:
    """One structured entry in the per-run guardrail event log (guardrail
    architecture item 19). `action` names what the engine actually did as
    a result (e.g. BLOCK_CALCULATION, FLAG_FOR_REVIEW, REQUIRE_APPROVAL,
    ALLOW) -- never left implicit in prose."""

    guardrail: str  # e.g. "DATA_CONFLICT", "EVIDENCE_OUTDATED", "ACTION_REQUIRES_APPROVAL"
    severity: Severity
    reason: str
    action: str
    metric: str | None = None
    sources: list[str] = field(default_factory=list)
    human_review_required: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "guardrail": self.guardrail,
            "severity": self.severity,
            "metric": self.metric,
            "sources": self.sources,
            "action": self.action,
            "reason": self.reason,
            "human_review_required": self.human_review_required,
        }


# ---------------------------------------------------------------------------
# Data conflict detail
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConflictingValue:
    value: Any
    source: str


@dataclass(frozen=True)
class DataConflict:
    metric: str
    values: list[ConflictingValue]
    period: str | None
    severity: Severity
    impact: str
    recommended_resolution: str = "Human verification required"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "DATA_CONFLICT",
            "metric": self.metric,
            "period": self.period,
            "severity": self.severity,
            "values": [{"value": v.value, "source": v.source} for v in self.values],
            "impact": self.impact,
            "action": self.recommended_resolution,
        }


# ---------------------------------------------------------------------------
# Data quality score (guardrail #8) -- a reliability indicator, never proof
# of compliance; see data_integrity.score_data_quality's docstring for the
# methodology behind each sub-score.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DataQualityScore:
    completeness: float
    consistency: float
    timeliness: float

    @property
    def overall(self) -> float:
        return round((self.completeness + self.consistency + self.timeliness) / 3, 1)

    def as_dict(self) -> dict[str, Any]:
        return {
            "completeness": self.completeness,
            "consistency": self.consistency,
            "timeliness": self.timeliness,
            "overall": self.overall,
        }


# ---------------------------------------------------------------------------
# Calculation result (guardrail #6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalculationResult:
    result: float | None
    formula: str
    inputs: dict[str, Any]
    units: str
    source_provenance: list[dict[str, Any]]
    validation_status: Literal["PASSED", "BLOCKED"]
    rejection_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "result": self.result,
            "formula": self.formula,
            "inputs": self.inputs,
            "units": self.units,
            "source_provenance": self.source_provenance,
            "validation_status": self.validation_status,
            "rejection_reason": self.rejection_reason,
        }


# ---------------------------------------------------------------------------
# Confidence (guardrail #13)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfidenceFactor:
    name: str
    met: bool
    detail: str


@dataclass(frozen=True)
class ConfidenceAssessment:
    level: ConfidenceLevel
    factors: list[ConfidenceFactor]
    methodology: str
    human_review_recommended: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "methodology": self.methodology,
            "human_review_recommended": self.human_review_recommended,
            "factors": [{"name": f.name, "met": f.met, "detail": f.detail} for f in self.factors],
        }


# ---------------------------------------------------------------------------
# Action authorization (guardrail #10)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActionRequest:
    action: str
    level: ActionLevel
    description: str
    requires_approval: bool
    approved: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "level": self.level,
            "description": self.description,
            "requires_approval": self.requires_approval,
            "approved": self.approved,
            "status": "ACTION_REQUIRES_APPROVAL" if self.requires_approval and not self.approved else "OK",
        }


# ---------------------------------------------------------------------------
# Evidence finding (guardrail #7)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceFinding:
    finding: str
    evidence_status: GuardrailStatus
    evidence_source: str | None
    evidence_date: str | None
    assessment_period: str | None
    confidence: ConfidenceLevel
    human_review_required: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "finding": self.finding,
            "evidence_status": self.evidence_status,
            "evidence_source": self.evidence_source,
            "evidence_date": self.evidence_date,
            "assessment_period": self.assessment_period,
            "confidence": self.confidence,
            "human_review_required": self.human_review_required,
        }


# ---------------------------------------------------------------------------
# Stop condition (guardrail #12)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StopDecision:
    should_stop: bool
    reason: str | None = None
