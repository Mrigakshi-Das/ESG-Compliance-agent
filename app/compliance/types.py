"""Shared data shapes passed between the compliance engine's stages
(app.compliance.engine -> gap_analysis -> prioritization -> recommendations)
so each stage can be tested against a hand-built `Gap` instead of needing a
full pipeline run.
"""

from dataclasses import dataclass, field
from typing import Any

from app.calculations.scoring import ComplianceStatus, PriorityLevel
from app.compliance.gap_analysis import RootCauseInvestigation


@dataclass
class Gap:
    plant: str
    period: str
    requirement_id: str
    regulation: str
    status: ComplianceStatus
    metric: str | None = None
    actual_value: float | None = None
    target_value: Any | None = None
    target_is_illustrative: bool = False
    variance_pct: float | None = None
    evidence_status: str | None = None
    missing_evidence: list[str] = field(default_factory=list)
    outdated_evidence: list[str] = field(default_factory=list)
    conflicting_evidence: list[Any] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    root_cause: RootCauseInvestigation | None = None
    estimated_impact: dict[str, Any] | None = None
    risk: float | None = None
    business_impact: float | None = None
    urgency: float | None = None
    priority_score: float | None = None
    priority_band: PriorityLevel | None = None
