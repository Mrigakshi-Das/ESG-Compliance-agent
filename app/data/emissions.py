"""GHG emissions data backend (Scope 1, Scope 2, total, sources).

Backs `app/tools/emissions.py`. Reads from the `emissions` table via
`app.data.db`.
"""

from typing import Any

from app.data.base import PlantDataSource
from app.data.db import fetch_all


class EmissionsDataSource(PlantDataSource):
    domain = "emissions"

    def fetch(self, plant: str, period: str | None = None) -> list[dict[str, Any]]:
        rows = [r for r in fetch_all("emissions") if r["plant_id"] == plant and r["period"] == period]
        return [
            {
                "plant_id": r["plant_id"],
                "period": r["period"],
                "scope_1_tco2e": float(r["scope_1_tco2e"]),
                "scope_2_tco2e": float(r["scope_2_tco2e"]),
                "total_tco2e": float(r["total_tco2e"]),
                "emission_sources": r["emission_sources"],
                "source_system": r["source_system"],
            }
            for r in rows
        ]
