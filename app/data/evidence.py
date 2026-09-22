"""Evidence/document repository backend (implements `DocumentSource`).

Backs `app/tools/documents.py` and `app/tools/evidence.py`. Reads document
metadata from the `evidence` table via `app.data.db`. A later phase can
point this at a real DMS/SharePoint without changing the tool layer.
"""

from typing import Any

from app.data.base import DocumentSource
from app.data.constants import PERIOD_CALENDAR
from app.data.db import fetch_all


def _covers_period(doc: dict[str, Any], period: str) -> bool:
    """A document is relevant to a period if it was issued during that
    period, or (for time-bound certificates) its validity window overlaps
    the period's calendar range."""
    if period not in PERIOD_CALENDAR:
        return False
    p_start, p_end = PERIOD_CALENDAR[period]
    doc_date = doc["document_date"]
    expiry = doc.get("expiry_date") or doc_date  # undated-expiry docs (filings) cover just their issue date
    return doc_date <= p_end and expiry >= p_start


class EvidenceDocumentSource(DocumentSource):
    def search(
        self,
        plant: str,
        document_type: str | None = None,
        period: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = [dict(r) for r in fetch_all("evidence") if r["plant_id"] == plant]

        if document_type:
            dt = document_type.lower()
            rows = [r for r in rows if dt in r["document_type"].lower()]

        if period:
            rows = [r for r in rows if _covers_period(r, period)]

        if keyword:
            kw = keyword.lower()
            rows = [
                r
                for r in rows
                if kw in r["document_type"].lower()
                or kw in r["related_requirement"].lower()
                or kw in r["document_id"].lower()
            ]

        return rows
