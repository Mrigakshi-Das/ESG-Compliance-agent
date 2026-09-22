"""Shared constants for the synthetic data layer: plants, reporting periods,
file locations, and the few cross-cutting assumptions (grid emission factor,
fossil fuel calorific value) used to keep generated figures internally
consistent. Used by the generator, the loader, and the validation tests.
"""

from pathlib import Path

APP_DATA_DIR = Path(__file__).resolve().parent
SEED_CSV_DIR = APP_DATA_DIR / "seed_csv"
DB_PATH = APP_DATA_DIR / "cement_esg.db"

PLANTS = ["Plant A", "Plant B", "Plant C"]

# Indian fiscal year (April-March) quarters. Six consecutive quarters give
# enough history to show a trend (Plant B's rising thermal energy) while
# leaving the two most recent quarters (FY2026-27 Q1/Q2) unreported, which
# is realistic for an assessment run partway through a fiscal year.
PERIODS = [
    "FY2024-25 Q3",
    "FY2024-25 Q4",
    "FY2025-26 Q1",
    "FY2025-26 Q2",
    "FY2025-26 Q3",
    "FY2025-26 Q4",
]

# Calendar month range for each period, used to place maintenance/evidence
# dates and to derive a period from a raw date.
PERIOD_CALENDAR = {
    "FY2024-25 Q3": ("2024-10-01", "2024-12-31"),
    "FY2024-25 Q4": ("2025-01-01", "2025-03-31"),
    "FY2025-26 Q1": ("2025-04-01", "2025-06-30"),
    "FY2025-26 Q2": ("2025-07-01", "2025-09-30"),
    "FY2025-26 Q3": ("2025-10-01", "2025-12-31"),
    "FY2025-26 Q4": ("2026-01-01", "2026-03-31"),
}

# Illustrative grid emission factor (tCO2e/MWh), approximating the direction
# (not the precise magnitude) of CEA's published CO2 baseline database
# year-on-year decline. Not a substitute for the actual CEA figure.
GRID_EMISSION_FACTOR_BY_FY = {
    "FY2024-25": 0.82,
    "FY2025-26": 0.79,
}

# Blended fossil fuel (coal + pet coke) calorific value assumption, used only
# to back-calculate a plausible fuel_consumption_tonnes from thermal energy
# and the alternative-fuel thermal substitution rate.
FOSSIL_FUEL_CALORIFIC_VALUE_GJ_PER_TONNE = 27.0


def fiscal_year_of(period: str) -> str:
    """"FY2025-26 Q2" -> "FY2025-26"."""
    return period.split(" ")[0]
