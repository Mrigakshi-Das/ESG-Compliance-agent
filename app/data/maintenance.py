"""Maintenance and instrument-calibration records backend.

Backs `app/tools/maintenance.py`, which the agent's root-cause analysis
uses to explain data/evidence gaps (e.g. "CEMS report missing" -> "sensor
calibration overdue"). Reads from the `maintenance` table via
`app.data.db`. Unlike the quarterly metric domains, records here are events,
not one-per-quarter facts, so `period=None` legitimately means "every
record for this plant" rather than a caller error.
"""

from typing import Any

from app.data.base import PlantDataSource
from app.data.db import fetch_all


class MaintenanceDataSource(PlantDataSource):
    domain = "maintenance"

    def fetch(self, plant: str, period: str | None = None) -> list[dict[str, Any]]:
        rows = [r for r in fetch_all("maintenance") if r["plant_id"] == plant]
        if period is not None:
            rows = [r for r in rows if r["period"] == period]
        return [dict(r) for r in rows]
