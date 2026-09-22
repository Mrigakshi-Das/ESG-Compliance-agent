"""Waste data backend (generated, recycled, utilized).

Backs `app/tools/waste.py`. Reads from the `waste` table via `app.data.db`.
"""

from typing import Any

from app.data.base import PlantDataSource
from app.data.db import fetch_all


class WasteDataSource(PlantDataSource):
    domain = "waste"

    def fetch(self, plant: str, period: str | None = None) -> list[dict[str, Any]]:
        rows = [r for r in fetch_all("waste") if r["plant_id"] == plant and r["period"] == period]
        return [
            {
                "plant_id": r["plant_id"],
                "period": r["period"],
                "waste_generated_tonnes": float(r["waste_generated_tonnes"]),
                "waste_recycled_tonnes": float(r["waste_recycled_tonnes"]),
                "waste_utilized_tonnes": float(r["waste_utilized_tonnes"]),
                "source_system": r["source_system"],
            }
            for r in rows
        ]
