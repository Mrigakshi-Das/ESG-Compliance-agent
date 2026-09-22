"""Data-quality engine: a structured, plant/period-level summary of what
Phase 3's tool layer already flags per call (missing/conflict statuses,
impossible-value and cross-check issues) plus duplicate-record detection in
the evidence repository.

Standalone and directly testable on its own -- it does not require an
agent run. `app.compliance.engine` calls it once per assessment and folds
its findings into the requirement-level gap analysis.
"""

from dataclasses import dataclass, field
from typing import Literal

from app.tools.documents import search_documents
from app.tools.emissions import get_emission_data
from app.tools.energy import get_energy_data
from app.tools.production import get_production_data
from app.tools.waste import get_waste_data
from app.tools.water import get_water_data

OverallQuality = Literal["Clean", "Issues Flagged", "Missing Data", "Conflicts Found"]

_DOMAIN_TOOLS = {
    "production": get_production_data,
    "energy": get_energy_data,
    "emissions": get_emission_data,
    "water": get_water_data,
    "waste": get_waste_data,
}


@dataclass
class DataQualityReport:
    plant: str
    period: str
    missing_domains: list[str] = field(default_factory=list)
    conflicting_domains: list[str] = field(default_factory=list)
    flagged_issues: dict[str, list[str]] = field(default_factory=dict)
    duplicate_documents: list[str] = field(default_factory=list)
    overall: OverallQuality = "Clean"


def assess_data_quality(plant: str, period: str) -> DataQualityReport:
    report = DataQualityReport(plant=plant, period=period)

    for domain, tool_fn in _DOMAIN_TOOLS.items():
        result = tool_fn(plant, period)
        if result["status"] == "missing":
            report.missing_domains.append(domain)
        elif result["status"] == "conflict":
            report.conflicting_domains.append(domain)
        if result["issues"]:
            report.flagged_issues[domain] = result["issues"]

    # Not period-filtered: a duplicate document_id is a repository-level
    # problem, not tied to whether that document happens to cover this
    # exact quarter (see app.compliance.engine for the same reasoning
    # applied to evidence assessment).
    documents = search_documents(plant)
    report.duplicate_documents = documents["duplicate_document_ids"]

    if report.conflicting_domains or report.duplicate_documents:
        report.overall = "Conflicts Found"
    elif report.missing_domains:
        report.overall = "Missing Data"
    elif report.flagged_issues:
        report.overall = "Issues Flagged"
    else:
        report.overall = "Clean"

    return report
