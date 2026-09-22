# Known Data Issues (ground truth)

Every deliberate data-quality problem in the synthetic dataset, catalogued
here rather than flagged inline in the CSVs — real messy data doesn't ship
with a column explaining itself, and the whole point of these rows is to
give the agent's future Data Validator (Phase 5/6) and Gap/Root-Cause
Analyzer (Phase 7) something real to find. Regenerating the data
(`python -m app.data.generate_synthetic_data`) reproduces every issue below
exactly, since nothing in the generator is randomized.

Reporting window: `FY2024-25 Q3` through `FY2025-26 Q4` (Oct 2024 – Mar
2026). "Today" for staleness/overdue checks is treated as **2026-09-12**.

## 1. Missing data — Plant C, production, FY2025-26 Q3

`production.csv` has no row at all for `Plant C` / `FY2025-26 Q3` — the
quarter was never posted/reconciled in the plant's production system.
`energy.csv`, `emissions.csv`, `water.csv`, and `waste.csv` **do** have a
`Plant C` / `FY2025-26 Q3` row, because meters and CEMS kept recording
regardless of the SAP posting gap. This is deliberate: it lets
`calculate_emission_intensity` (Phase 3) be exercised against a real case
where the numerator (emissions) exists but the denominator (production)
does not — the correct behavior is to raise/flag "Data Missing", never to
guess a production figure.

## 2. Conflicting data — Plant C, production, FY2025-26 Q2

`production.csv` has **two** rows for `Plant C` / `FY2025-26 Q2`, one per
source system, with different figures:

| source_system | clinker_production_tonnes | cement_production_tonnes |
|---|---|---|
| `SAP_PP` | 152,000 | 181,500 |
| `ESG_Portal` | 149,500 | 179,800 |

A ~1.6% discrepancy — plausible as an unreconciled correction or rounding
difference between the plant's production system and its ESG reporting
portal, not a wild/obviously-fabricated mismatch. A correct reader must
surface this as a conflict rather than silently averaging or picking one.

## 3. Duplicate record — Plant C, evidence, `DOC-C-2026-014`

`evidence.csv` has two rows sharing the same `document_id`
(`DOC-C-2026-014`, a CEMS Calibration Certificate for Plant C), with a
2-day discrepancy in `document_date`/`expiry_date` (2026-04-03 vs
2026-04-05) — representing the same physical certificate re-ingested by a
document-management pipeline. Distinct from issue #2: here the *key*
collides (same document_id), not just the values.

## 4. Outdated (expired) evidence — Plant B, Environmental Clearance

`evidence.csv` row `DOC-B-2025-005` (Environmental Clearance Renewal) has
`expiry_date = 2025-04-01` and `status = Expired` — over a year lapsed as of
2026-09-12, with no renewal on file. Distinct from a *missing* document:
this one exists and is stale, which should read as "Evidence Missing /
Outdated" rather than simply absent.

## 5. Missing evidence — Plant B, CEMS calibration (two quarters)

`evidence.csv` has no CEMS Calibration Certificate for Plant B after
`DOC-B-2025-004` (calibrated 2025-09-10, valid to 2026-03-10). This lines up
exactly with `maintenance.csv`, where Plant B's "Stack CEMS Analyzer"
calibration is `Overdue` (`planned_next_maintenance = 2026-03-10`, never
performed) — a case where the evidence gap has a traceable operational root
cause, not just a filing oversight.

## 6. Missing evidence (filing gap only) — Plant A, FY2025-26 Q4

Plant A has no CEMS Calibration Certificate for the quarter ending Mar 2026,
**but** `maintenance.csv` confirms the calibration itself was performed on
schedule (2026-03-25, `status = Completed`). This is a pure
documentation/evidence-repository gap with no underlying operational
problem — included specifically so the agent must distinguish "Evidence
Missing" (a filing gap) from a genuine "Potential Gap" (an operational
shortfall). Plant A is otherwise the strongest performer of the three.

## 7. Impossible value — Plant B, waste, FY2025-26 Q3

`waste.csv`: `waste_generated_tonnes = 610`, `waste_recycled_tonnes =
683.2` — recycled waste exceeds waste generated in the same quarter, which
is not physically possible. A logical-constraint violation, not just a
statistical outlier; a validator should reject/flag this rather than
average it away.

## 8. Abnormal value (real anomaly, not a data error) — Plant B, energy, FY2025-26 Q2

`energy.csv`: `specific_electricity_consumption_kwh_per_t_cement` jumps to
**118** for Plant B in FY2025-26 Q2, versus 95–99 in every other quarter.
Unlike issue #7, this is not a data-entry mistake — it is a real,
explainable spike: `maintenance.csv` shows an unplanned "Raw Mill Motor
Bearing (Line 2)" breakdown dated 2025-08-18 (within this same quarter)
that caused several weeks of reduced-capacity, less-efficient operation.
`production.csv` corroborates it: `operating_days` for this plant/quarter
drops to 79 (vs. 84–88 elsewhere) and output is lower. This triple
corroboration (energy anomaly + maintenance record + lower operating days)
is the intended input to a root-cause investigation
("Why did Plant B's specific energy consumption spike?").

## 9. Sustained trend, not a single bad value — Plant B, thermal energy & Scope 1

Plant B's `specific_thermal_energy_consumption_gj_per_t_clinker` rises every
single quarter (3.55 → 3.60 → 3.65 → 3.72 → 3.82 → 3.90), and its Scope 1
emission factor rises in step (0.900 → 0.975 tCO2e/t clinker). This is
deliberately a *trend*, not an anomaly in one period — it should be read
differently from issue #8, and its likely root cause
(`maintenance.csv`: Kiln Refractory Lining inspection `Overdue` since
2025-06-15) is a genuine, unaddressed degradation rather than a one-off
event.

## 10. Second, independent contributing factor — Plant B, fuel quality, all six quarters

Alongside issue #9's overdue Kiln Refractory Lining, Plant B's kiln fuel
blend also genuinely degrades over the same window: `fuel_quality.csv`
shows `gross_calorific_value_kcal_per_kg` falling from 4780 to 4300
(-10.0%) and `ash_content_pct` rising from 17.5 to 21.2 (+21.1%) —
consistent with a supplier blend drifting to lower-grade coal/pet coke.
This is deliberately a *second, independent* real driver of the same
rising thermal SEC, not a restatement of issue #9 — a correct root-cause
investigation should surface both the maintenance-linked hypothesis and
this fuel-quality-linked one, and should not treat finding one as license
to stop looking for the other. Added specifically to give root-cause
investigation a genuine correlation candidate outside the original
production → electricity → thermal energy → fuel → maintenance chain (see
`app.compliance.gap_analysis`'s `_EXTERNAL_FACTOR_CHAIN`).

Plant B's `weather.csv` rainfall/humidity, by contrast, happen to *fall*
across the same window — the *helpful* direction, not a contributing
factor — and a correct investigation must not report them as if they
explained the rise. This is a deliberate check on over-eager correlation:
not every notable co-movement is a real contributing factor.

## Coverage against the required data-quality test categories

| Category | Where |
|---|---|
| Missing data | #1 (production), and evidence gaps in #5/#6 |
| Outdated evidence | #4 |
| Conflicting data | #2 |
| Abnormal / impossible values | #7 (impossible), #8 (abnormal but real) |
| Duplicate records | #3 (and #2 doubles as a duplicate natural key: same plant+period, two rows) |

## Per-plant summary (matches the brief's narrative)

- **Plant A** — best performer on every metric (lowest emission/energy
  intensity, highest renewable share and alt-fuel substitution); one pure
  evidence-filing gap (#6).
- **Plant B** — highest emission intensity, a worsening thermal-efficiency
  trend (#9) with two independent, identified but unaddressed root causes
  (overdue kiln maintenance, and a declining fuel quality blend, #10), an
  unplanned energy anomaly (#8), overdue maintenance on two pieces of
  equipment, an expired clearance (#4), and a missing recent calibration
  certificate (#5), plus one impossible data value (#7).
- **Plant C** — mid-tier, otherwise unremarkable performance; its problems
  are entirely in the data pipeline, not the plant (#1, #2, #3).
