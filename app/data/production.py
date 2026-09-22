"""Production data backend (clinker/cement production, production units).

Backs `app/tools/production.py`. Reads from the `production` table (built
from `app/data/seed_csv/production.csv`) via `app.data.db`.
"""

from typing import Any

from app.data.base import PlantDataSource
from app.data.db import fetch_all


class ProductionDataSource(PlantDataSource):
    domain = "production"

    def fetch(self, plant: str, period: str | None = None) -> list[dict[str, Any]]:
        rows = [r for r in fetch_all("production") if r["plant_id"] == plant and r["period"] == period]
        return [
            {
                "plant_id": r["plant_id"],
                "period": r["period"],
                "clinker_production_tonnes": float(r["clinker_production_tonnes"]),
                "cement_production_tonnes": float(r["cement_production_tonnes"]),
                "operating_days": int(float(r["operating_days"])),
                "source_system": r["source_system"],
            }
            for r in rows
        ]
