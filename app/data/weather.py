"""Ambient weather data backend (temperature, rainfall, humidity).

Backs `app/tools/weather.py`. Reads from the `weather` table (built from
`app/data/seed_csv/weather.csv`) via `app.data.db`.
"""

from typing import Any

from app.data.base import PlantDataSource
from app.data.db import fetch_all


class WeatherDataSource(PlantDataSource):
    domain = "weather"

    def fetch(self, plant: str, period: str | None = None) -> list[dict[str, Any]]:
        rows = [r for r in fetch_all("weather") if r["plant_id"] == plant and r["period"] == period]
        return [
            {
                "plant_id": r["plant_id"],
                "period": r["period"],
                "avg_ambient_temp_c": float(r["avg_ambient_temp_c"]),
                "rainfall_mm": float(r["rainfall_mm"]),
                "avg_humidity_pct": float(r["avg_humidity_pct"]),
                "source_system": r["source_system"],
            }
            for r in rows
        ]
