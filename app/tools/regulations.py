"""Tool: search_regulations.

Backed by the sourced regulatory knowledge base built in Phase 4
(`app.regulations.repository`, covering BEE PAT, BEE CCTS, SEBI BRSR, and
SEBI BRSR Core) -- replacing the Phase 2 `regulatory_targets` placeholder
table per the swap Phase 1's architecture called for: same tool signature,
real sourced backend. Never invents a requirement: only returns records
that exist in the knowledge base, each carrying its own source and a
staleness flag.
"""

from dataclasses import asdict
from typing import Any

from app.regulations.repository import search
from app.tools.errors import ToolInputError
from app.tools.schema import ToolParam, ToolSpec

_SUPPORTED_INDUSTRIES = {"cement"}

# Mirrors the "today" convention used elsewhere in the prototype (see
# app/data/validate_data.py, app/tools/evidence.py) for staleness checks.
TODAY_ISO = "2026-09-12"

COMPLIANCE_DISCLAIMER = (
    "Compliance readiness assessment based on the configured regulatory knowledge base. "
    "This is not a determination of legal compliance."
)

SEARCH_REGULATIONS_SPEC = ToolSpec(
    name="search_regulations",
    description="Search the regulatory knowledge base for requirements matching a topic.",
    inputs=[
        ToolParam(
            "topic", "str", True,
            "Free-text topic, matched case-insensitively against regulation name, metric, "
            "and requirement description, e.g. 'emission', 'energy', 'disclosure', 'assurance'.",
        ),
        ToolParam("industry", "str", False, "Defaults to 'cement', the only industry currently covered."),
        ToolParam("reporting_period", "str", False, "If given, only requirements whose reporting_period text mentions it."),
    ],
    output_description=(
        "{status: 'ok'|'no_matches', topic, regulations: list[dict], notice: str}. Each "
        "regulation dict is a full RegulatoryRequirement record plus `potentially_outdated: bool` "
        "(last_reviewed more than 365 days before today). `notice` is the fixed compliance-"
        "readiness disclaimer, always present."
    ),
    raises="ToolInputError if industry is not 'cement', or topic is blank.",
)


def search_regulations(
    topic: str,
    industry: str = "cement",
    reporting_period: str | None = None,
) -> dict[str, Any]:
    if not topic or not topic.strip():
        raise ToolInputError("topic must be a non-empty string.")
    if industry.lower() not in _SUPPORTED_INDUSTRIES:
        raise ToolInputError(f"Unsupported industry {industry!r}; only {_SUPPORTED_INDUSTRIES} is covered.")

    matches = search(topic, reporting_period=reporting_period)

    regulations = []
    for r in matches:
        record = asdict(r)
        record["potentially_outdated"] = r.is_potentially_outdated(TODAY_ISO)
        regulations.append(record)

    return {
        "status": "ok" if regulations else "no_matches",
        "topic": topic,
        "regulations": regulations,
        "notice": COMPLIANCE_DISCLAIMER,
    }
