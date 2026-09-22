"""Tool: search_documents.

Agent-callable wrapper around `app.data.evidence.EvidenceDocumentSource`.
Flags duplicate `document_id`s found within the result set (see
KNOWN_DATA_ISSUES.md #3) -- never silently deduplicates them.
"""

from collections import Counter
from typing import Any

from app.data.evidence import EvidenceDocumentSource
from app.tools._common import validate_period, validate_plant
from app.tools.schema import ToolParam, ToolSpec

_source = EvidenceDocumentSource()

SEARCH_DOCUMENTS_SPEC = ToolSpec(
    name="search_documents",
    description="Search the evidence/document repository for one plant, optionally filtered by type, period, or keyword.",
    inputs=[
        ToolParam("plant", "str", True, "One of the configured plant identifiers."),
        ToolParam("document_type", "str", False, "Substring match against document type, e.g. 'CEMS Calibration'."),
        ToolParam("period", "str", False, "A configured fiscal-quarter period; documents whose validity window covers it."),
        ToolParam("keyword", "str", False, "Substring match against document type, related requirement, or document ID."),
    ],
    output_description=(
        "{status: 'ok'|'no_records', plant, documents: list[dict], "
        "duplicate_document_ids: list[str], issues: list[str]}. An empty result "
        "is a normal 'nothing matched' outcome, not itself a data-quality flag."
    ),
    raises="ToolInputError if plant is unknown, or period is given and not one of the configured values.",
)


def search_documents(
    plant: str,
    document_type: str | None = None,
    period: str | None = None,
    keyword: str | None = None,
) -> dict[str, Any]:
    validate_plant(plant)
    if period is not None:
        validate_period(period)

    documents = _source.search(plant, document_type=document_type, period=period, keyword=keyword)

    id_counts = Counter(d["document_id"] for d in documents)
    duplicate_ids = sorted(doc_id for doc_id, count in id_counts.items() if count > 1)
    issues = []
    if duplicate_ids:
        issues.append(
            f"document_id(s) {duplicate_ids} appear more than once in the result set -- "
            "treat as a duplicate record, not confirmation from two sources."
        )

    return {
        "status": "ok" if documents else "no_records",
        "plant": plant,
        "documents": documents,
        "duplicate_document_ids": duplicate_ids,
        "issues": issues,
    }
