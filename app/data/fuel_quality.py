"""Kiln fuel quality data backend (calorific value, ash/moisture/sulphur
content).

Backs `app/tools/fuel_quality.py`. Reads from the `fuel_quality` table
(built from `app/data/seed_csv/fuel_quality.csv`) via `app.data.db`.
"""

from typing import Any

from app.data.base import PlantDataSource
from app.data.db import fetch_all


class FuelQualityDataSource(PlantDataSource):
    domain = "fuel_quality"

    def fetch(self, plant: str, period: str | None = None) -> list[dict[str, Any]]:
        rows = [r for r in fetch_all("fuel_quality") if r["plant_id"] == plant and r["period"] == period]
        return [
            {
                "plant_id": r["plant_id"],
                "period": r["period"],
                "gross_calorific_value_kcal_per_kg": float(r["gross_calorific_value_kcal_per_kg"]),
                "ash_content_pct": float(r["ash_content_pct"]),
                "moisture_content_pct": float(r["moisture_content_pct"]),
                "sulphur_content_pct": float(r["sulphur_content_pct"]),
                "source_system": r["source_system"],
            }
            for r in rows
        ]
