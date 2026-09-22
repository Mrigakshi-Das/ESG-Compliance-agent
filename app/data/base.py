"""Shared interface for plant data sources.

Every domain module in this package (production.py, energy.py, emissions.py,
water.py, waste.py, maintenance.py, evidence.py) implements this interface
against synthetic CSV/SQLite data for the prototype. Swapping in SAP, an
IoT/CEMS feed, or an enterprise ESG database later means writing a new class
that implements the same interface -- nothing in `app/tools`, `app/agent`,
or `app/compliance` needs to change.

`fetch` returns a **list** of raw rows, not a single dict. Phase 2's dataset
established that a (plant, period) key can genuinely map to zero rows (not
yet posted), one row (the normal case), or more than one (duplicate/
conflicting source systems) -- the data layer reports exactly what it finds
and does no interpretation. Deciding what 0/1/N rows *means*
(Data Missing / ok / Conflicting Data) is `app.tools`'s job, one layer up,
because that is the agent-facing boundary where "validate inputs, handle
missing data, identify conflicting data" (the Phase 3 tool contract)
applies -- not the data layer's, which should behave like a real backend
that just answers the query it was given.
"""

from abc import ABC, abstractmethod
from typing import Any


class PlantDataSource(ABC):
    """Interface for a domain-specific plant data backend.

    `domain` identifies what this source serves (e.g. "production",
    "energy") purely for logging/diagnostics -- it is not used for
    dispatch, since each domain gets its own concrete subclass.
    """

    domain: str

    @abstractmethod
    def fetch(self, plant: str, period: str | None = None) -> list[dict[str, Any]]:
        """Return every raw row matching plant (and period, if given).

        Never raises for "no such data" -- returns an empty list. Never
        merges, picks, or averages when multiple rows match; returns all of
        them so the caller can see and report the conflict. `period=None`
        is only meaningful for backends where records aren't one-per-quarter
        (e.g. maintenance events); period-bound domains should treat a
        missing period as a caller error.
        """
        raise NotImplementedError


class DocumentSource(ABC):
    """Interface for the evidence/document repository backend.

    Concrete implementation in Phase 2 reads document metadata (name, date,
    validity, source) from the synthetic dataset. A later phase can point
    this at SharePoint, a DMS, or an object store without changing
    `app/tools/documents.py` or `app/tools/evidence.py`.
    """

    @abstractmethod
    def search(
        self,
        plant: str,
        document_type: str | None,
        period: str | None,
        keyword: str | None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError
