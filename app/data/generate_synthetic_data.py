"""Generates the synthetic Cement ESG dataset: 10 CSVs under seed_csv/, then
loads them into a SQLite database at cement_esg.db.

Design intent
-------------
Every plant/period's production, energy, and emissions figures are derived
from a small set of hand-authored "driver" values (production volumes,
specific energy consumption, emission factors, renewable share, thermal
substitution rate) using fixed formulas -- nothing here is randomly sampled.
This keeps the numbers internally consistent (e.g. Plant B's rising thermal
energy consumption necessarily raises its Scope 1 emissions) instead of
independently-random columns that would not tell a coherent story.

A handful of rows deliberately break that consistency on purpose, to give
the (future) agent real data-quality problems to detect. Every one of them
is catalogued in KNOWN_DATA_ISSUES.md with the exact plant/period/field and
why it's there -- this script does not "flag" them inline, because real
messy data doesn't ship with a note explaining itself.

Run with: python -m app.data.generate_synthetic_data
"""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from datetime import date

from app.data.constants import (
    DB_PATH,
    FOSSIL_FUEL_CALORIFIC_VALUE_GJ_PER_TONNE,
    GRID_EMISSION_FACTOR_BY_FY,
    PERIOD_CALENDAR,
    PERIODS,
    PLANTS,
    SEED_CSV_DIR,
    fiscal_year_of,
)

# ---------------------------------------------------------------------------
# Per-plant, per-period driver values (index i corresponds to PERIODS[i]).
# Hand-authored, not random -- see module docstring.
# ---------------------------------------------------------------------------


@dataclass
class PlantProfile:
    clinker_t: list[float]
    cement_t: list[float]
    operating_days: list[int]
    thermal_sec_gj_per_t_clinker: list[float]
    electrical_sec_kwh_per_t_cement: list[float]
    renewable_share: list[float]
    scope1_factor_tco2e_per_t_clinker: list[float]
    alt_fuel_thermal_substitution: list[float]
    water_withdrawal_m3: list[float]
    water_consumption_fraction: list[float]
    water_recycled_fraction: list[float]
    waste_generated_t: list[float]
    waste_recycled_fraction: list[float]
    waste_utilized_fraction: list[float]
    emission_sources: str
    # Fuel quality (kiln fuel blend) and ambient weather -- added to give
    # root-cause investigation genuinely new, ungrounded-nothing correlation
    # candidates beyond the original production/electricity/thermal/fuel/
    # maintenance chain. Not used as a formula input into thermal energy
    # (thermal_sec_gj_per_t_clinker above remains the sole driver of the
    # energy/emissions figures) -- these are independent, correlatable
    # signals, same as any other driver series here.
    gcv_kcal_per_kg: list[float]
    ash_content_pct: list[float]
    moisture_content_pct: list[float]
    sulphur_content_pct: list[float]
    avg_ambient_temp_c: list[float]
    rainfall_mm: list[float]
    avg_humidity_pct: list[float]


PROFILES: dict[str, PlantProfile] = {
    # Plant A: modern, well-run -- consistently the best performer, small
    # steady efficiency gains every quarter, high alternative-fuel use.
    "Plant A": PlantProfile(
        clinker_t=[292000, 295000, 298000, 300000, 303000, 305000],
        cement_t=[430000, 435000, 440000, 445000, 448000, 452000],
        operating_days=[89, 90, 91, 90, 92, 90],
        thermal_sec_gj_per_t_clinker=[3.05, 3.03, 3.01, 2.99, 2.97, 2.95],
        electrical_sec_kwh_per_t_cement=[78.5, 78.0, 77.5, 77.0, 76.5, 76.0],
        renewable_share=[0.08, 0.09, 0.10, 0.12, 0.13, 0.14],
        scope1_factor_tco2e_per_t_clinker=[0.790, 0.785, 0.780, 0.775, 0.770, 0.765],
        alt_fuel_thermal_substitution=[0.28, 0.29, 0.30, 0.32, 0.33, 0.35],
        water_withdrawal_m3=[142000, 143000, 144000, 145000, 146000, 147000],
        water_consumption_fraction=[0.56, 0.56, 0.55, 0.55, 0.54, 0.54],
        water_recycled_fraction=[0.33, 0.34, 0.35, 0.36, 0.37, 0.38],
        waste_generated_t=[460, 465, 470, 468, 472, 475],
        waste_recycled_fraction=[0.68, 0.69, 0.70, 0.71, 0.72, 0.73],
        waste_utilized_fraction=[0.18, 0.18, 0.19, 0.19, 0.19, 0.19],
        emission_sources="Kiln fuel combustion; Calcination (process emissions); Captive diesel genset (standby only)",
        # Fuel sourcing steadily improving, consistent with best-performer status.
        gcv_kcal_per_kg=[5180, 5200, 5220, 5240, 5260, 5280],
        ash_content_pct=[14.5, 14.3, 14.0, 13.8, 13.5, 13.2],
        moisture_content_pct=[6.2, 6.0, 5.9, 5.8, 5.6, 5.5],
        sulphur_content_pct=[0.62, 0.61, 0.60, 0.60, 0.59, 0.58],
        avg_ambient_temp_c=[27.5, 22.0, 32.5, 31.0, 28.0, 21.5],
        rainfall_mm=[120, 25, 40, 650, 140, 20],
        avg_humidity_pct=[58, 45, 42, 78, 60, 44],
    ),
    # Plant B: older, under-maintained -- thermal SEC and Scope 1 factor
    # both climb every quarter (declining kiln/refractory condition).
    # FY2025-26 Q2 (index 3) carries a raw-mill bearing failure: lower
    # production, lower operating days, and a genuine electricity-SEC spike
    # (a real anomaly, not a data error). Its fuel quality also genuinely
    # declines over the same six quarters (a supplier blend drifting to
    # lower-grade coal/pet-coke) -- a second, independent, real contributing
    # factor to the rising thermal SEC, alongside the overdue kiln
    # refractory lining. See KNOWN_DATA_ISSUES.md issue #10.
    "Plant B": PlantProfile(
        clinker_t=[206000, 204000, 202000, 185000, 198000, 196000],
        cement_t=[222000, 220000, 218000, 196000, 214000, 212000],
        operating_days=[88, 87, 86, 79, 85, 84],
        thermal_sec_gj_per_t_clinker=[3.55, 3.60, 3.65, 3.72, 3.82, 3.90],
        electrical_sec_kwh_per_t_cement=[96, 95, 97, 118, 98, 99],
        renewable_share=[0.03, 0.03, 0.03, 0.03, 0.03, 0.03],
        scope1_factor_tco2e_per_t_clinker=[0.900, 0.910, 0.925, 0.940, 0.960, 0.975],
        alt_fuel_thermal_substitution=[0.10, 0.10, 0.09, 0.09, 0.08, 0.08],
        water_withdrawal_m3=[118000, 117000, 116000, 110000, 115000, 114000],
        water_consumption_fraction=[0.62, 0.63, 0.63, 0.60, 0.64, 0.64],
        water_recycled_fraction=[0.09, 0.09, 0.10, 0.10, 0.10, 0.11],
        waste_generated_t=[610, 615, 620, 590, 610, 615],
        # index 4 (FY2025-26 Q3) = 1.12 -> recycled > generated: a deliberate
        # impossible value. See KNOWN_DATA_ISSUES.md.
        waste_recycled_fraction=[0.55, 0.56, 0.57, 0.55, 1.12, 0.58],
        waste_utilized_fraction=[0.12, 0.12, 0.12, 0.12, 0.10, 0.12],
        emission_sources="Kiln fuel combustion; Calcination (process emissions); Standby DG sets (extended use during grid outages)",
        # Deliberate: GCV falls ~10% and ash content rises ~21% over six
        # quarters -- a real, findable secondary driver of the rising
        # thermal SEC, independent of the maintenance story above.
        gcv_kcal_per_kg=[4780, 4700, 4600, 4500, 4400, 4300],
        ash_content_pct=[17.5, 18.2, 19.0, 19.8, 20.5, 21.2],
        moisture_content_pct=[8.0, 8.1, 8.3, 8.4, 8.6, 8.8],
        sulphur_content_pct=[0.88, 0.90, 0.92, 0.95, 0.97, 1.00],
        avg_ambient_temp_c=[27.0, 21.5, 33.0, 31.5, 27.5, 21.0],
        rainfall_mm=[110, 20, 35, 610, 130, 18],
        avg_humidity_pct=[56, 43, 41, 76, 58, 42],
    ),
    # Plant C: mid-tier and broadly stable. Its data problems are in the
    # production records, not the plant's actual performance.
    "Plant C": PlantProfile(
        clinker_t=[151000, 153000, 155000, 152000, 157000, 158000],
        cement_t=[180000, 182000, 184000, 181500, 186500, 188000],
        operating_days=[87, 88, 89, 88, 89, 90],
        thermal_sec_gj_per_t_clinker=[3.28, 3.27, 3.26, 3.25, 3.24, 3.23],
        electrical_sec_kwh_per_t_cement=[86, 85.5, 85, 85, 84.5, 84],
        renewable_share=[0.06, 0.07, 0.07, 0.08, 0.08, 0.09],
        scope1_factor_tco2e_per_t_clinker=[0.845, 0.842, 0.840, 0.838, 0.836, 0.834],
        alt_fuel_thermal_substitution=[0.15, 0.16, 0.16, 0.17, 0.17, 0.18],
        water_withdrawal_m3=[96000, 97000, 98000, 99000, 99500, 100500],
        water_consumption_fraction=[0.58, 0.58, 0.57, 0.57, 0.57, 0.56],
        water_recycled_fraction=[0.22, 0.23, 0.24, 0.24, 0.25, 0.26],
        waste_generated_t=[340, 345, 348, 350, 352, 355],
        waste_recycled_fraction=[0.60, 0.61, 0.62, 0.62, 0.63, 0.64],
        waste_utilized_fraction=[0.15, 0.15, 0.16, 0.16, 0.16, 0.17],
        emission_sources="Kiln fuel combustion; Calcination (process emissions); Captive diesel genset (standby only)",
        gcv_kcal_per_kg=[4950, 4945, 4940, 4945, 4950, 4955],
        ash_content_pct=[16.0, 16.0, 15.9, 15.9, 15.8, 15.8],
        moisture_content_pct=[7.2, 7.1, 7.1, 7.0, 7.0, 6.9],
        sulphur_content_pct=[0.75, 0.75, 0.74, 0.74, 0.73, 0.73],
        avg_ambient_temp_c=[27.2, 21.8, 32.0, 30.5, 27.8, 21.2],
        rainfall_mm=[115, 22, 38, 630, 135, 19],
        avg_humidity_pct=[57, 44, 42, 77, 59, 43],
    ),
}

# Plant C, index 3 (FY2025-26 Q2): two source systems disagree on production
# for the same plant/period -- SAP (plant DB) vs the ESG reporting portal.
# The profile's clinker_t[3]/cement_t[3] above (152000/181500) are the SAP
# figures; this is the ESG portal's competing figure. See
# KNOWN_DATA_ISSUES.md.
PLANT_C_ESG_PORTAL_CONFLICT = {"clinker_t": 149500, "cement_t": 179800}

# Plant C, index 4 (FY2025-26 Q3): production was never posted/reconciled in
# SAP for this quarter, so no production.csv row exists for it at all --
# even though the plant physically operated and its meters/CEMS kept
# recording energy and emissions. clinker_t[4]/cement_t[4] in the profile
# above are used only to derive that quarter's energy/emissions/water/waste
# rows; they are intentionally never written to production.csv.
PLANT_C_MISSING_PRODUCTION_INDEX = 4


def date_to_period(d: date) -> str:
    iso = d.isoformat()
    for period, (start, end) in PERIOD_CALENDAR.items():
        if start <= iso <= end:
            return period
    return "Unreported (outside FY2024-25 Q3 - FY2025-26 Q4 window)"


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------


def build_production_rows() -> list[dict]:
    rows = []
    for plant in PLANTS:
        profile = PROFILES[plant]
        for i, period in enumerate(PERIODS):
            if plant == "Plant C" and i == PLANT_C_MISSING_PRODUCTION_INDEX:
                continue  # deliberately missing -- see KNOWN_DATA_ISSUES.md
            rows.append(
                {
                    "plant_id": plant,
                    "period": period,
                    "clinker_production_tonnes": profile.clinker_t[i],
                    "cement_production_tonnes": profile.cement_t[i],
                    "operating_days": profile.operating_days[i],
                    "source_system": "SAP_PP",
                }
            )
            if plant == "Plant C" and i == 3:
                # Deliberate duplicate/conflicting record: a second source
                # system reports different figures for the same plant+period.
                rows.append(
                    {
                        "plant_id": plant,
                        "period": period,
                        "clinker_production_tonnes": PLANT_C_ESG_PORTAL_CONFLICT["clinker_t"],
                        "cement_production_tonnes": PLANT_C_ESG_PORTAL_CONFLICT["cement_t"],
                        "operating_days": profile.operating_days[i],
                        "source_system": "ESG_Portal",
                    }
                )
    return rows


def build_energy_rows() -> list[dict]:
    rows = []
    for plant in PLANTS:
        p = PROFILES[plant]
        for i, period in enumerate(PERIODS):
            clinker, cement = p.clinker_t[i], p.cement_t[i]
            thermal_energy_gj = round(clinker * p.thermal_sec_gj_per_t_clinker[i], 1)
            electricity_mwh = round(cement * p.electrical_sec_kwh_per_t_cement[i] / 1000, 1)
            renewable_mwh = round(electricity_mwh * p.renewable_share[i], 1)
            tsr = p.alt_fuel_thermal_substitution[i]
            fossil_thermal_gj = thermal_energy_gj * (1 - tsr)
            fuel_tonnes = round(fossil_thermal_gj / FOSSIL_FUEL_CALORIFIC_VALUE_GJ_PER_TONNE, 1)
            rows.append(
                {
                    "plant_id": plant,
                    "period": period,
                    "electricity_consumption_mwh": electricity_mwh,
                    "thermal_energy_gj": thermal_energy_gj,
                    "fuel_consumption_tonnes": fuel_tonnes,
                    "alternative_fuel_thermal_substitution_pct": round(tsr * 100, 1),
                    "renewable_energy_mwh": renewable_mwh,
                    "specific_electricity_consumption_kwh_per_t_cement": p.electrical_sec_kwh_per_t_cement[i],
                    "specific_thermal_energy_consumption_gj_per_t_clinker": p.thermal_sec_gj_per_t_clinker[i],
                    "source_system": "Energy_Meters_CEMS",
                }
            )
    return rows


def build_emissions_rows() -> list[dict]:
    rows = []
    for plant in PLANTS:
        p = PROFILES[plant]
        for i, period in enumerate(PERIODS):
            clinker, cement = p.clinker_t[i], p.cement_t[i]
            electricity_mwh = cement * p.electrical_sec_kwh_per_t_cement[i] / 1000
            renewable_mwh = electricity_mwh * p.renewable_share[i]
            grid_electricity_mwh = electricity_mwh - renewable_mwh
            grid_factor = GRID_EMISSION_FACTOR_BY_FY[fiscal_year_of(period)]
            scope1 = round(clinker * p.scope1_factor_tco2e_per_t_clinker[i], 1)
            scope2 = round(grid_electricity_mwh * grid_factor, 1)
            rows.append(
                {
                    "plant_id": plant,
                    "period": period,
                    "scope_1_tco2e": scope1,
                    "scope_2_tco2e": scope2,
                    "total_tco2e": round(scope1 + scope2, 1),
                    "emission_sources": p.emission_sources,
                    "source_system": "CEMS_and_Utility_Bills",
                }
            )
    return rows


def build_water_rows() -> list[dict]:
    rows = []
    for plant in PLANTS:
        p = PROFILES[plant]
        for i, period in enumerate(PERIODS):
            withdrawal = p.water_withdrawal_m3[i]
            consumption = round(withdrawal * p.water_consumption_fraction[i], 1)
            recycled = round(withdrawal * p.water_recycled_fraction[i], 1)
            intensity = round(consumption / p.cement_t[i], 4)
            rows.append(
                {
                    "plant_id": plant,
                    "period": period,
                    "water_withdrawal_m3": withdrawal,
                    "water_consumption_m3": consumption,
                    "recycled_water_m3": recycled,
                    "water_intensity_m3_per_t_cement": intensity,
                    "source_system": "Water_Meters",
                }
            )
    return rows


def build_waste_rows() -> list[dict]:
    rows = []
    for plant in PLANTS:
        p = PROFILES[plant]
        for i, period in enumerate(PERIODS):
            generated = p.waste_generated_t[i]
            recycled = round(generated * p.waste_recycled_fraction[i], 1)
            utilized = round(generated * p.waste_utilized_fraction[i], 1)
            rows.append(
                {
                    "plant_id": plant,
                    "period": period,
                    "waste_generated_tonnes": generated,
                    "waste_recycled_tonnes": recycled,
                    "waste_utilized_tonnes": utilized,
                    "source_system": "Waste_Management_Register",
                }
            )
    return rows


def build_fuel_quality_rows() -> list[dict]:
    rows = []
    for plant in PLANTS:
        p = PROFILES[plant]
        for i, period in enumerate(PERIODS):
            rows.append(
                {
                    "plant_id": plant,
                    "period": period,
                    "gross_calorific_value_kcal_per_kg": p.gcv_kcal_per_kg[i],
                    "ash_content_pct": p.ash_content_pct[i],
                    "moisture_content_pct": p.moisture_content_pct[i],
                    "sulphur_content_pct": p.sulphur_content_pct[i],
                    "source_system": "Fuel_Lab_QC",
                }
            )
    return rows


def build_weather_rows() -> list[dict]:
    rows = []
    for plant in PLANTS:
        p = PROFILES[plant]
        for i, period in enumerate(PERIODS):
            rows.append(
                {
                    "plant_id": plant,
                    "period": period,
                    "avg_ambient_temp_c": p.avg_ambient_temp_c[i],
                    "rainfall_mm": p.rainfall_mm[i],
                    "avg_humidity_pct": p.avg_humidity_pct[i],
                    "source_system": "Site_Weather_Station",
                }
            )
    return rows


def build_maintenance_rows() -> list[dict]:
    def row(plant, equipment, m_date, m_type, status, issue, next_date):
        return {
            "plant_id": plant,
            "equipment": equipment,
            "maintenance_date": m_date,
            "period": date_to_period(date.fromisoformat(m_date)),
            "maintenance_type": m_type,
            "maintenance_status": status,
            "issue": issue,
            "planned_next_maintenance": next_date,
        }

    return [
        row(
            "Plant A", "Kiln ESP (Electrostatic Precipitator)", "2025-11-12",
            "Preventive", "Completed", "Routine electrode cleaning and inspection",
            "2026-05-12",
        ),
        row(
            "Plant A", "CEMS Stack Analyzer", "2026-03-25",
            "Calibration", "Completed",
            "Routine 6-month recalibration per CPCB CEMS protocol; completed on schedule",
            "2026-09-25",
        ),
        row(
            "Plant A", "Raw Mill Drive Motor", "2026-03-02",
            "Preventive", "Completed", "Bearing lubrication and vibration check",
            "2026-12-02",
        ),
        row(
            "Plant B", "Kiln Refractory Lining", "2024-12-15",
            "Inspection", "Overdue",
            "Refractory wear accelerating; relining inspection deferred twice due to "
            "production schedule pressure -- contributing to rising kiln thermal "
            "energy consumption",
            "2025-06-15",
        ),
        row(
            "Plant B", "Stack CEMS Analyzer (SO2/NOx/PM)", "2025-09-10",
            "Calibration", "Overdue",
            "Mandatory 6-month recalibration under CPCB CEMS protocol not completed; "
            "current stack monitoring data cannot be certified",
            "2026-03-10",
        ),
        row(
            "Plant B", "Raw Mill Motor Bearing (Line 2)", "2025-08-18",
            "Breakdown/Corrective", "Completed",
            "Unplanned bearing failure caused ~3 weeks of reduced-capacity operation "
            "and elevated specific electricity consumption",
            "2026-08-18",
        ),
        row(
            "Plant C", "Kiln ESP (Electrostatic Precipitator)", "2025-10-05",
            "Preventive", "Completed", "Routine electrode cleaning and inspection",
            "2026-04-05",
        ),
        row(
            "Plant C", "CEMS Stack Analyzer", "2026-03-20",
            "Calibration", "Completed",
            "Routine 6-month recalibration per CPCB CEMS protocol; completed on schedule",
            "2026-09-20",
        ),
    ]


def build_evidence_rows() -> list[dict]:
    def row(doc_id, plant, doc_type, doc_date, expiry, status, requirement):
        return {
            "document_id": doc_id,
            "plant_id": plant,
            "document_type": doc_type,
            "document_date": doc_date,
            "expiry_date": expiry,
            "status": status,
            "related_requirement": requirement,
        }

    rows = [
        # --- Plant A: clean record except one filing gap (see below) ---
        row("DOC-A-2025-001", "Plant A", "BRSR Annual Report", "2025-05-28", "", "Valid", "SEBI BRSR - Annual Disclosure"),
        row("DOC-A-2025-002", "Plant A", "GHG Verification Statement", "2025-06-10", "", "Valid", "SEBI BRSR Core - GHG Assurance"),
        row("DOC-A-2025-003", "Plant A", "CEMS Calibration Certificate", "2025-04-18", "2025-10-18", "Valid", "CPCB CEMS Monitoring"),
        row("DOC-A-2025-004", "Plant A", "CEMS Calibration Certificate", "2025-07-20", "2026-01-20", "Valid", "CPCB CEMS Monitoring"),
        row("DOC-A-2025-005", "Plant A", "CEMS Calibration Certificate", "2025-10-22", "2026-04-22", "Valid", "CPCB CEMS Monitoring"),
        # No CEMS Calibration Certificate on file for the Mar-2026 calibration
        # (maintenance.csv confirms the calibration itself was performed) --
        # deliberate Evidence Missing gap. See KNOWN_DATA_ISSUES.md.
        row("DOC-A-2025-006", "Plant A", "BRSR Annual Report", "2026-05-30", "", "Valid", "SEBI BRSR - Annual Disclosure"),
        row("DOC-A-2025-007", "Plant A", "Environmental Clearance Renewal", "2022-03-01", "2027-03-01", "Valid", "State PCB - Environmental Clearance"),

        # --- Plant B: expired clearance + missing recent calibration ---
        row("DOC-B-2025-001", "Plant B", "BRSR Annual Report", "2025-05-30", "", "Valid", "SEBI BRSR - Annual Disclosure"),
        row("DOC-B-2025-002", "Plant B", "GHG Verification Statement", "2025-06-15", "", "Valid", "SEBI BRSR Core - GHG Assurance"),
        row("DOC-B-2025-003", "Plant B", "CEMS Calibration Certificate", "2025-04-05", "2025-10-05", "Valid", "CPCB CEMS Monitoring"),
        row("DOC-B-2025-004", "Plant B", "CEMS Calibration Certificate", "2025-09-10", "2026-03-10", "Valid", "CPCB CEMS Monitoring"),
        # No certificate after this -- matches the Overdue calibration in
        # maintenance.csv. Deliberate Evidence Missing gap.
        row("DOC-B-2025-005", "Plant B", "Environmental Clearance Renewal", "2020-04-01", "2025-04-01", "Expired", "State PCB - Environmental Clearance"),
        row("DOC-B-2025-006", "Plant B", "BRSR Annual Report", "2026-06-05", "", "Valid", "SEBI BRSR - Annual Disclosure"),
        row("DOC-B-2025-007", "Plant B", "GHG Verification Statement", "2026-06-20", "", "Valid", "SEBI BRSR Core - GHG Assurance"),

        # --- Plant C: clean documents plus one duplicated record ---
        row("DOC-C-2025-001", "Plant C", "BRSR Annual Report", "2025-05-25", "", "Valid", "SEBI BRSR - Annual Disclosure"),
        row("DOC-C-2025-002", "Plant C", "GHG Verification Statement", "2025-06-08", "", "Valid", "SEBI BRSR Core - GHG Assurance"),
        row("DOC-C-2025-010", "Plant C", "CEMS Calibration Certificate", "2025-04-12", "2025-10-12", "Valid", "CPCB CEMS Monitoring"),
        row("DOC-C-2026-014", "Plant C", "CEMS Calibration Certificate", "2026-04-03", "2026-10-03", "Valid", "CPCB CEMS Monitoring"),
        # Deliberate duplicate: same document_id re-ingested with a 2-day
        # date discrepancy (document management system duplication bug).
        row("DOC-C-2026-014", "Plant C", "CEMS Calibration Certificate", "2026-04-05", "2026-10-05", "Valid", "CPCB CEMS Monitoring"),
        row("DOC-C-2025-005", "Plant C", "BRSR Annual Report", "2026-05-29", "", "Valid", "SEBI BRSR - Annual Disclosure"),
        row("DOC-C-2025-006", "Plant C", "GHG Verification Statement", "2026-06-12", "", "Valid", "SEBI BRSR Core - GHG Assurance"),
    ]
    return rows


def build_regulatory_targets_rows() -> list[dict]:
    note = "Synthetic placeholder for the Phase 2 prototype -- to be replaced with the sourced record in the Phase 4 regulatory knowledge base."
    return [
        {
            "regulation": "BEE PAT Cycle VII (illustrative)",
            "applicability": "Plant A - PAT Designated Consumer",
            "metric": "Specific Thermal Energy Consumption",
            "target": "3.00",
            "unit": "GJ per tonne clinker",
            "effective_period": "FY2025-26",
            "source_reference": note,
        },
        {
            "regulation": "BEE PAT Cycle VII (illustrative)",
            "applicability": "Plant B - PAT Designated Consumer",
            "metric": "Specific Thermal Energy Consumption",
            "target": "3.40",
            "unit": "GJ per tonne clinker",
            "effective_period": "FY2025-26",
            "source_reference": note,
        },
        {
            "regulation": "BEE CCTS (illustrative)",
            "applicability": "All plants - GHG emission intensity benchmark",
            "metric": "GHG Emission Intensity",
            "target": "0.780",
            "unit": "tCO2e per tonne cementitious product",
            "effective_period": "FY2025-26 onward (compliance year to be notified)",
            "source_reference": note,
        },
        {
            "regulation": "SEBI BRSR Core (illustrative)",
            "applicability": "Listed entity - GHG disclosure",
            "metric": "Scope 1 + Scope 2 GHG Intensity Disclosure",
            "target": "Mandatory disclosure with reasonable assurance",
            "unit": "N/A",
            "effective_period": "FY2025-26 (BRSR Core assurance)",
            "source_reference": note,
        },
        {
            "regulation": "SEBI BRSR (illustrative)",
            "applicability": "Listed entity - Renewable energy disclosure",
            "metric": "Renewable Energy Share of Total Energy",
            "target": "Disclosure only (no fixed numeric target)",
            "unit": "N/A",
            "effective_period": "FY2025-26",
            "source_reference": note,
        },
        {
            "regulation": "Environmental (future module, illustrative)",
            "applicability": "All plants - stack particulate matter",
            "metric": "Stack PM Emission Limit",
            "target": "30",
            "unit": "mg/Nm3",
            "effective_period": "Ongoing",
            "source_reference": note + " Represents a future non-MVP module per the Phase 1 architecture.",
        },
    ]


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

TABLES: dict[str, list[dict]] = {}  # populated in main()


def write_csv(name: str, rows: list[dict]) -> None:
    path = SEED_CSV_DIR / f"{name}.csv"
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_sqlite_db() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    try:
        for name, rows in TABLES.items():
            columns = list(rows[0].keys())
            col_defs = ", ".join(f'"{c}" TEXT' for c in columns)
            conn.execute(f'CREATE TABLE "{name}" ({col_defs})')
            placeholders = ", ".join("?" for _ in columns)
            conn.executemany(
                f'INSERT INTO "{name}" VALUES ({placeholders})',
                [[row[c] for c in columns] for row in rows],
            )
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    SEED_CSV_DIR.mkdir(parents=True, exist_ok=True)

    TABLES["production"] = build_production_rows()
    TABLES["energy"] = build_energy_rows()
    TABLES["emissions"] = build_emissions_rows()
    TABLES["water"] = build_water_rows()
    TABLES["waste"] = build_waste_rows()
    TABLES["fuel_quality"] = build_fuel_quality_rows()
    TABLES["weather"] = build_weather_rows()
    TABLES["maintenance"] = build_maintenance_rows()
    TABLES["evidence"] = build_evidence_rows()
    TABLES["regulatory_targets"] = build_regulatory_targets_rows()

    for name, rows in TABLES.items():
        write_csv(name, rows)

    build_sqlite_db()

    total_rows = sum(len(rows) for rows in TABLES.values())
    print(f"Wrote {len(TABLES)} CSVs ({total_rows} rows total) to {SEED_CSV_DIR}")
    print(f"Built SQLite database at {DB_PATH}")


if __name__ == "__main__":
    main()
