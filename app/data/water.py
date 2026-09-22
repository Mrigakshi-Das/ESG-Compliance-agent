"""Water data backend (withdrawal, consumption, recycled, intensity).

Backs `app/tools/water.py`. Reads from the `water` table via `app.data.db`.
"""

from typing import Any

from app.data.base import PlantDataSource
from app.data.db import fetch_all


class WaterDataSource(PlantDataSource):
    domain = "water"

    def fetch(self, plant: str, period: str | None = None) -> list[dict[str, Any]]:
        rows = [r for r in fetch_all("water") if r["plant_id"] == plant and r["period"] == period]
        return [
            {
                "plant_id": r["plant_id"],
                "period": r["period"],
                "water_withdrawal_m3": float(r["water_withdrawal_m3"]),
                "water_consumption_m3": float(r["water_consumption_m3"]),
                "recycled_water_m3": float(r["recycled_water_m3"]),
                "water_intensity_m3_per_t_cement": float(r["water_intensity_m3_per_t_cement"]),
                "source_system": r["source_system"],
            }
            for r in rows
        ]
