# Data Dictionary — Synthetic Cement ESG Dataset

Source of truth: `app/data/generate_synthetic_data.py` (regenerate with
`python -m app.data.generate_synthetic_data`). Output: 10 CSVs under
`app/data/seed_csv/` and a mirror SQLite database at
`app/data/cement_esg.db` (one table per CSV, same columns, all stored as
`TEXT` — type coercion is the caller's job, deliberately, so a malformed
value surfaces instead of being silently cast).

Scope: 3 plants (`Plant A`, `Plant B`, `Plant C`) × 6 fiscal-quarter periods
(`FY2024-25 Q3` … `FY2025-26 Q4`, Indian FY = April–March). See
[KNOWN_DATA_ISSUES.md](KNOWN_DATA_ISSUES.md) for every place a table
deliberately deviates from a clean 3×6 grid.

All regulatory figures in this dataset (`regulatory_targets.csv`) are
**synthetic placeholders for the prototype**, not real BEE/SEBI figures —
see that table's note below.

---

## production.csv / `production` table

One row per plant per period reported by the plant's production system,
except where deliberately missing or duplicated (see issues #1, #2).

| Field | Unit | Description |
|---|---|---|
| `plant_id` | — | `Plant A` / `Plant B` / `Plant C` |
| `period` | — | Fiscal quarter, e.g. `FY2025-26 Q2` |
| `clinker_production_tonnes` | tonnes | Clinker produced in the period |
| `cement_production_tonnes` | tonnes | Cement produced in the period (> clinker, reflecting blended/composite cement with fly ash or slag) |
| `operating_days` | days | Days the plant operated in the period (out of ~90) |
| `source_system` | — | `SAP_PP` (plant production system) or `ESG_Portal` (ESG reporting portal) — see issue #2 for why both appear |

## energy.csv / `energy` table

One row per plant per period, sourced from energy meters/CEMS — present
even for the one period where `production.csv` has no matching row
(issue #1), since metering doesn't stop just because a production figure
wasn't posted.

| Field | Unit | Description |
|---|---|---|
| `plant_id`, `period` | — | Same as above |
| `electricity_consumption_mwh` | MWh | Total electricity consumed (grid + captive renewable) |
| `thermal_energy_gj` | GJ | Kiln thermal energy input |
| `fuel_consumption_tonnes` | tonnes | Conventional fossil fuel (coal + pet coke, blended) consumed; back-calculated from thermal energy net of alternative-fuel substitution, assuming a blended calorific value of 27 GJ/tonne |
| `alternative_fuel_thermal_substitution_pct` | % | Share of thermal energy from alternative fuels (RDF, tyres, biomass) instead of fossil fuel |
| `renewable_energy_mwh` | MWh | Portion of `electricity_consumption_mwh` from renewable sources |
| `specific_electricity_consumption_kwh_per_t_cement` | kWh/t cement | Electrical intensity as reported by the plant |
| `specific_thermal_energy_consumption_gj_per_t_clinker` | GJ/t clinker | Thermal intensity as reported by the plant |
| `source_system` | — | Always `Energy_Meters_CEMS` in this dataset |

`specific_electricity_consumption_kwh_per_t_cement` and
`specific_thermal_energy_consumption_gj_per_t_clinker` are the plant's own
reported intensities — they are provided here as source data, not computed
by the agent. Phase 3's `calculate_energy_intensity` recomputes the same
figure independently from `electricity_consumption_mwh` /
`cement_production_tonnes`, so the two can be cross-checked.

## emissions.csv / `emissions` table

One row per plant per period.

| Field | Unit | Description |
|---|---|---|
| `plant_id`, `period` | — | Same as above |
| `scope_1_tco2e` | tCO2e | Direct emissions: kiln fuel combustion + calcination process emissions, `= clinker_production_tonnes × plant's Scope 1 emission factor` |
| `scope_2_tco2e` | tCO2e | Indirect emissions from purchased grid electricity, `= (electricity_consumption_mwh − renewable_energy_mwh) × grid emission factor` (0.82 tCO2e/MWh for FY2024-25 periods, 0.79 for FY2025-26 — an illustrative approximation of the direction of India's CEA CO2-baseline-database trend, not the exact published figure) |
| `total_tco2e` | tCO2e | `scope_1_tco2e + scope_2_tco2e` |
| `emission_sources` | — | Semicolon-separated list of the major contributing sources |
| `source_system` | — | Always `CEMS_and_Utility_Bills` in this dataset |

## water.csv / `water` table

| Field | Unit | Description |
|---|---|---|
| `plant_id`, `period` | — | Same as above |
| `water_withdrawal_m3` | m³ | Total water withdrawn (all sources) |
| `water_consumption_m3` | m³ | Withdrawn water not returned to source (a plant-specific fraction of withdrawal — lower is better) |
| `recycled_water_m3` | m³ | Withdrawn water recycled/reused on-site |
| `water_intensity_m3_per_t_cement` | m³/t cement | `water_consumption_m3 / cement_production_tonnes` |
| `source_system` | — | Always `Water_Meters` |

## waste.csv / `waste` table

| Field | Unit | Description |
|---|---|---|
| `plant_id`, `period` | — | Same as above |
| `waste_generated_tonnes` | tonnes | Solid waste generated (kiln dust, refractory, packaging, sludge) |
| `waste_recycled_tonnes` | tonnes | Waste recycled/reused on-site — see issue #7 for one deliberately impossible value (`> waste_generated_tonnes`) |
| `waste_utilized_tonnes` | tonnes | Waste utilized externally (e.g. co-processed by a third party) |
| `source_system` | — | Always `Waste_Management_Register` |

## fuel_quality.csv / `fuel_quality` table

One row per plant per period, sourced from the kiln fuel lab's QC log.
Added so root-cause investigation has real, grounded correlation
candidates outside the original production/electricity/thermal/fuel/
maintenance chain — see `app.compliance.gap_analysis`'s
`_EXTERNAL_FACTOR_CHAIN`. Not used as a formula input into
`thermal_energy_gj` or any other energy/emissions figure; these are
independent, correlatable driver values, same as every other series in
this dataset (see the module docstring in `generate_synthetic_data.py`).

| Field | Unit | Description |
|---|---|---|
| `plant_id`, `period` | — | Same as above |
| `gross_calorific_value_kcal_per_kg` | kcal/kg | Calorific value of the kiln fuel blend (coal + pet coke) — Plant B's genuinely declines ~10% over the dataset's window; see [KNOWN_DATA_ISSUES.md](KNOWN_DATA_ISSUES.md) issue #10 |
| `ash_content_pct` | % | Ash content of the fuel blend — lower is better for combustion efficiency |
| `moisture_content_pct` | % | Moisture content of the fuel blend |
| `sulphur_content_pct` | % | Sulphur content of the fuel blend |
| `source_system` | — | Always `Fuel_Lab_QC` in this dataset |

## weather.csv / `weather` table

One row per plant per period, sourced from the site weather station.
Same rationale as `fuel_quality.csv` above — a genuinely new correlation
candidate (raw-material moisture from rainfall/humidity potentially
raising drying energy load), not a formula input into any other table.

| Field | Unit | Description |
|---|---|---|
| `plant_id`, `period` | — | Same as above |
| `avg_ambient_temp_c` | °C | Average ambient temperature for the period |
| `rainfall_mm` | mm | Total rainfall for the period |
| `avg_humidity_pct` | % | Average ambient relative humidity for the period |
| `source_system` | — | Always `Site_Weather_Station` in this dataset |

## maintenance.csv / `maintenance` table

Equipment maintenance and instrument-calibration event log — this is what
the agent's root-cause analysis (Phase 7) draws on to explain a gap.

| Field | Unit | Description |
|---|---|---|
| `plant_id` | — | Plant the equipment belongs to |
| `equipment` | — | Equipment/instrument name |
| `maintenance_date` | date (ISO) | Date the event occurred |
| `period` | — | Fiscal quarter `maintenance_date` falls into, derived from `PERIOD_CALENDAR` in `app/data/constants.py` |
| `maintenance_type` | — | `Preventive` / `Calibration` / `Inspection` / `Breakdown/Corrective` |
| `maintenance_status` | — | `Completed` or `Overdue` |
| `issue` | — | Free-text description of what was found/done |
| `planned_next_maintenance` | date (ISO) | Next due date; a past date with `maintenance_status = Overdue` means it was never carried out |

## evidence.csv / `evidence` table

Document repository metadata — no document *content*, only what a real DMS
index would hold.

| Field | Unit | Description |
|---|---|---|
| `document_id` | — | Document identifier. Not unique in this dataset — see issue #3 |
| `plant_id` | — | Plant the document pertains to |
| `document_type` | — | e.g. `BRSR Annual Report`, `CEMS Calibration Certificate`, `GHG Verification Statement`, `Environmental Clearance Renewal` |
| `document_date` | date (ISO) | Date the document was issued |
| `expiry_date` | date (ISO) or blank | Blank for filings that don't expire (annual reports, assurance statements); populated for time-bound certificates/clearances |
| `status` | — | `Valid`, `Expired`, or `Pending Renewal` |
| `related_requirement` | — | Free-text link to the regulatory requirement this document evidences (matches a `regulation`/category in `regulatory_targets.csv` or the Phase 4 knowledge base) |

## regulatory_targets.csv / `regulatory_targets` table

**Synthetic placeholders for this prototype phase** — illustrative numbers
in the shape of real BEE/SEBI requirements, not sourced regulatory text.
Every row's `source_reference` says so explicitly. Phase 4 replaces this
table with the full sourced regulatory knowledge base defined in the
Phase 1 architecture (`app/regulations/bee.py`, `sebi.py`,
`environmental.py`), each record carrying an authoritative source document,
version date, and last-reviewed date.

| Field | Description |
|---|---|
| `regulation` | Regulation/scheme name (marked "illustrative") |
| `applicability` | Which plant(s)/entity type the row applies to |
| `metric` | What is measured |
| `target` | Numeric target, or a qualitative disclosure requirement where there is no fixed number |
| `unit` | Unit of `target`, or `N/A` for qualitative rows |
| `effective_period` | Fiscal year(s) the target applies to |
| `source_reference` | Placeholder note (see above) |
