"""Tool: assess_evidence.

Compares a regulatory requirement's evidence needs against documents
returned by `search_documents` (`app.tools.documents`). Pure comparison
logic over already-retrieved documents -- it does not query the document
repository itself, so it can be unit-tested against hand-built document
lists without touching the dataset.
"""

from collections import Counter
from datetime import date
from typing import Any

from app.tools.errors import ToolInputError
from app.tools.schema import ToolParam, ToolSpec

# Mirrors the "today" assumption used throughout the Phase 2 dataset
# (see app/data/validate_data.py) for expiry/staleness comparisons.
DEFAULT_AS_OF_DATE = "2026-09-12"

ASSESS_EVIDENCE_SPEC = ToolSpec(
    name="assess_evidence",
    description=(
        "Compare a requirement's required evidence document types against a set of "
        "already-retrieved documents (from search_documents) and classify coverage."
    ),
    inputs=[
        ToolParam(
            "requirement", "dict", True,
            "{'required_document_types': list[str], 'as_of_date': str (ISO, optional)}.",
        ),
        ToolParam("available_documents", "list[dict]", True, "Documents as returned by search_documents()['documents']."),
    ],
    output_description=(
        "{evidence_status: 'Compliant'|'Missing'|'Outdated'|'Conflicting'|'Mixed', "
        "missing_evidence: list[str], outdated_evidence: list[dict], "
        "conflicting_evidence: list[dict], matched_evidence: list[dict]}."
    ),
    raises="ToolInputError if requirement has no required_document_types, or as_of_date is unparseable.",
)


def assess_evidence(
    requirement: dict[str, Any],
    available_documents: list[dict[str, Any]],
) -> dict[str, Any]:
    required_types = requirement.get("required_document_types")
    if not required_types:
        raise ToolInputError("requirement['required_document_types'] must be a non-empty list.")

    as_of_raw = requirement.get("as_of_date", DEFAULT_AS_OF_DATE)
    try:
        as_of = date.fromisoformat(as_of_raw)
    except (TypeError, ValueError) as exc:
        raise ToolInputError(f"requirement['as_of_date'] must be an ISO date string, got {as_of_raw!r}") from exc

    missing_evidence: list[str] = []
    outdated_evidence: list[dict[str, Any]] = []
    conflicting_evidence: list[dict[str, Any]] = []
    matched_evidence: list[dict[str, Any]] = []

    for doc_type in required_types:
        matches = [d for d in available_documents if doc_type.lower() in d["document_type"].lower()]

        if not matches:
            missing_evidence.append(doc_type)
            continue

        id_counts = Counter(d["document_id"] for d in matches)
        duplicate_ids = {doc_id for doc_id, count in id_counts.items() if count > 1}
        if duplicate_ids:
            conflicting_evidence.append(
                {
                    "document_type": doc_type,
                    "document_ids": sorted(duplicate_ids),
                    "reason": "Duplicate document_id in the matched evidence set.",
                }
            )
            continue

        # Most recent match by document_date represents current coverage.
        current = max(matches, key=lambda d: d["document_date"])
        is_expired = current.get("status") == "Expired" or (
            current.get("expiry_date") and date.fromisoformat(current["expiry_date"]) < as_of
        )
        if is_expired:
            outdated_evidence.append(current)
        else:
            matched_evidence.append(current)

    if conflicting_evidence:
        evidence_status = "Conflicting"
    elif missing_evidence and len(missing_evidence) == len(required_types):
        evidence_status = "Missing"
    elif missing_evidence or outdated_evidence:
        evidence_status = "Mixed" if matched_evidence else ("Missing" if missing_evidence else "Outdated")
    else:
        evidence_status = "Compliant"

    return {
        "evidence_status": evidence_status,
        "missing_evidence": missing_evidence,
        "outdated_evidence": outdated_evidence,
        "conflicting_evidence": conflicting_evidence,
        "matched_evidence": matched_evidence,
    }
