"""Energy data backend (electricity, fuel, renewable share, thermal energy).

Backs `app/tools/energy.py`. Reads from the `energy` table via `app.data.db`.
"""

from typing import Any

from app.data.base import PlantDataSource
from app.data.db import fetch_all

_NUMERIC_FIELDS = (
    "electricity_consumption_mwh",
    "thermal_energy_gj",
    "fuel_consumption_tonnes",
    "alternative_fuel_thermal_substitution_pct",
    "renewable_energy_mwh",
    "specific_electricity_consumption_kwh_per_t_cement",
    "specific_thermal_energy_consumption_gj_per_t_clinker",
)


class EnergyDataSource(PlantDataSource):
    domain = "energy"

    def fetch(self, plant: str, period: str | None = None) -> list[dict[str, Any]]:
        rows = [r for r in fetch_all("energy") if r["plant_id"] == plant and r["period"] == period]
        result = []
        for r in rows:
            row = {"plant_id": r["plant_id"], "period": r["period"], "source_system": r["source_system"]}
            row.update({field: float(r[field]) for field in _NUMERIC_FIELDS})
            result.append(row)
        return result
