"""The report's data shape: one dataclass per the Phase 7 brief's 13
sections, all nested under `ComplianceReport`. Every field is built from
data already produced by `app.compliance.engine` / `app.reports.scoring` /
`app.reports.kpi_dashboard` -- this module holds no logic of its own, only
the shape, so `dataclasses.asdict(report)` is always a complete, correct
JSON export.
"""

from dataclasses import dataclass, field
from typing import Any

from app.compliance.data_quality import DataQualityReport
from app.compliance.types import Gap
from app.reports.kpi_dashboard import KPIEntry
from app.reports.scoring import CategoryScore

COMPLIANCE_DISCLAIMER = (
    "Compliance readiness assessment based on the configured regulatory knowledge base. "
    "This is not a determination of legal compliance."
)


@dataclass
class SourceCitation:
    source_id: str
    title: str
    authority: str
    url: str
    date: str
    cited_by: list[str] = field(default_factory=list)


@dataclass
class HypothesisEntry:
    statement: str
    confidence: str  # "Medium" (tied to a specific corroborating record) or "Low" (no corroboration found)


@dataclass
class RootCauseSection:
    requirement_id: str
    metric: str
    trend: str
    facts: list[str] = field(default_factory=list)
    hypotheses: list[HypothesisEntry] = field(default_factory=list)


@dataclass
class EvidenceStatusEntry:
    requirement_id: str
    regulation: str
    evidence_status: str | None
    missing_evidence: list[str] = field(default_factory=list)
    outdated_evidence: list[str] = field(default_factory=list)
    conflicting_evidence: list[Any] = field(default_factory=list)


@dataclass
class ComplianceReport:
    plant: str
    period: str
    generated_at: str
    disclaimer: str

    executive_summary: str
    readiness_score: dict[str, Any]  # {"overall_score": float, "breakdown": list[CategoryScore]}
    kpi_dashboard: list[KPIEntry]
    applicable_requirements: list[dict[str, Any]]
    compliance_status: dict[str, str]
    key_gaps: list[Gap]
    root_cause_analysis: list[RootCauseSection]
    priority_actions: list[dict[str, Any]]
    evidence_status: list[EvidenceStatusEntry]
    data_quality_issues: DataQualityReport
    assumptions: list[str]
    sources: list[SourceCitation]
    human_review_required: list[dict[str, Any]]
