# Test Results

```
$ python -m app.data.generate_synthetic_data && python -m pytest -q
450 passed in ~6s
```

Run from a freshly regenerated database (`app/data/cement_esg.db` deleted
and rebuilt from `seed_csv/*.csv`) immediately before this count was taken,
to confirm the suite passes from a clean start, not just against
already-warm local state.

## Breakdown by area

| File | Tests | Covers |
|---|--:|---|
| `test_synthetic_data.py` | 22 | Every CSV loads and is non-empty (10 domains, incl. fuel_quality/weather); SQLite matches CSV; structural checks; all 9 documented data-quality issues are actually present |
| `test_calculations.py` | 21 | `app/calculations/*.py` — emission/energy intensity, variance/target comparison, priority scoring; invalid-input error cases |
| `test_tools_domain_data.py` | 30 | `get_production_data`, `get_energy_data`, `get_emission_data`, `get_water_data`, `get_waste_data`, `get_fuel_quality_data`, `get_weather_data`, `get_maintenance_data` — valid input, missing/conflicting data, known impossible values, invalid plant/period |
| `test_tools_docs_regs_evidence.py` | 21 | `search_documents`, `search_regulations`, `assess_evidence` — every evidence status branch (Compliant/Missing/Outdated/Conflicting/Mixed), source citations, staleness flagging |
| `test_tools_analytics.py` | 12 | `get_historical_metric` (trend detection), `compare_plants` (ranking, unavailable-plant exclusion) |
| `test_regulations.py` | 23 | The Phase 4 knowledge base and applicability engine — every requirement resolves to a defensible verdict, never a guess |
| `test_agent_planner.py` | 29 | `parse_objective` / `build_plan` / `infer_metric_key` — intent classification across all ~11 intents (incl. `external_action_request`), metric keyword mapping |
| `test_agent_orchestrator.py` | 22 | Full `run()` demonstrations (the worked examples in [DEMO.md](DEMO.md) and more), evidence-audit and energy-metric regression tests, stopping conditions |
| `test_agent_llm_client.py` | 8 | The optional Claude tool-use loop's control flow (turn dispatch, max-turn cap) against a scripted fake client — no network access needed |
| `test_compliance_requirements.py` | 6 | Applicability resolution: PAT/CCTS always Cannot Determine, BRSR/BRSR Core under the documented demo assumption, identical results across all 3 plants |
| `test_compliance_data_quality.py` | 6 | `assess_data_quality` — Clean/Issues Flagged/Missing Data/Conflicts Found summarization |
| `test_compliance_gap_analysis.py` | 27 | `classify_requirement_status` (8-status vocabulary, severity ordering) + `investigate_root_cause` (Fact/Hypothesis typing, confidence levels, the fuel-quality/weather external-factor scan, and the optional LLM-assisted exploration stage against a scripted fake client) |
| `test_compliance_prioritization.py` | 7 | Risk × Business Impact × Urgency scoring and banding |
| `test_compliance_recommendations.py` | 8 | Corrective-action generation, grounded (never-invented) impact estimates |
| `test_compliance_engine.py` | 15 | `run_compliance_assessment` end-to-end wiring, operational-benchmark gaps, evidence-type matching |
| `test_reports_scoring.py` | 10 | Category-weighted readiness score, custom weight overrides, error cases |
| `test_reports_kpi_dashboard.py` | 6 | KPI dashboard entry construction |
| `test_reports_generator.py` | 19 | Full 13-section report assembly; JSON/Markdown/PDF rendering; Fact/Hypothesis confidence survives into the rendered report |
| `test_ui_server.py` | 20 | Every Flask route — static pages, `/api/run` for each assessment type, missing-data handling, PDF export, error responses for bad input |
| `test_guardrails_data_integrity.py` | 18 | Guardrails #1/#2/#8 — tool-result classification, provenance tagging, `DataConflict` construction, `DataQualityScore` |
| `test_guardrails_source_validation.py` | 12 | Guardrail #3 — Tier 1/2/3 classification, including the real-KB authority-string substring-match fix |
| `test_guardrails_regulatory_validation.py` | 13 | Guardrail #4 — CURRENT/OUTDATED/FUTURE_EFFECTIVE/UNKNOWN classification from real `RegulatoryRequirement` fields |
| `test_guardrails_calculation_safety.py` | 8 | Guardrail #6 — structured calculation results, incompatible-period/plant rejection |
| `test_guardrails_evidence_validation.py` | 11 | Guardrail #7 — EVIDENCE_* mapping, "no evidence != compliant" |
| `test_guardrails_confidence.py` | 9 | Guardrail #13 — the five-factor transparent confidence methodology |
| `test_guardrails_action_authorization.py` | 13 | Guardrail #10 — Level 1/2/3 classification, approval gating |
| `test_guardrails_stop_conditions.py` | 11 | Guardrail #12 — every named stop condition |
| `test_guardrails_output_validation.py` | 11 | Guardrail #14 — legal-compliance phrasing, undisclosed conflicts, unapproved-action claims |
| `test_guardrails_engine.py` | 11 | `GuardrailEngine` integration — event logging, dashboard payload, confidence integration |
| `test_guardrails_scenarios.py` | 21 | The 15 end-to-end guardrail scenarios (TEST 1–15) from the Phase 12 brief, run against the real orchestrator and real dataset wherever a natural case exists |
| **Total** | **450** | |

## What's deliberately *not* covered by an automated scenario scorecard

The original project brief also called for a separate 8-dimension
evaluation scorecard (tool-selection accuracy, calculation accuracy,
regulatory-retrieval accuracy, gap-identification accuracy, recommendation
quality, data-quality handling, missing-information handling, end-to-end
completion) scored across 10+ named scenarios. That module exists as a
documented stub —
[app/evaluation/evaluation_metrics/scorecard.py](../app/evaluation/evaluation_metrics/scorecard.py)
raises `NotImplementedError` on both its functions — rather than a
half-built approximation. The 450 tests above already exercise all 8 of
those dimensions as pytest assertions (see the table), just not packaged as
a standalone scored report. Building that report is scoped out of this
phase; see [ROADMAP.md](ROADMAP.md).

## Manual verification performed

Beyond the automated suite, the following were checked by hand against the
running UI (not just unit-tested in isolation):

- The exact demonstration query from [DEMO.md](DEMO.md), run through both
  `app.agent.orchestrator.run()` directly and the live control-tower UI,
  confirming the UI's rendered Key Gaps table, root-cause flow (with
  Fact/Hypothesis confidence labels), and readiness gauge all match what the
  backend actually computed.
- A full clean-start rehearsal: delete `cement_esg.db` → regenerate →
  validate → run the full suite → start the UI, with zero manual
  intervention required at any step.
- Every Flask route was checked for unhandled-exception exposure (found and
  fixed one gap on `/api/report.pdf`; see [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)).
- The new "Guardrails & Reliability" UI panel, run live against Plant B's
  full assessment: confirmed the four progress bars, the Human Review
  pill, and the recent-events list all reflect real guardrail engine
  output (a genuine `REGULATION_OUTDATED` finding traced to an actual
  `superseded_or_amended_by` field already in the sourced knowledge base,
  not a fabricated demo value) — see [GUARDRAILS.md](GUARDRAILS.md).
- A real bug was found this way and fixed before shipping: the source-tier
  classifier initially required an *exact* match against a short authority
  name, so every real BEE/SEBI source in the KB (whose `authority` field
  reads e.g. "Bureau of Energy Efficiency (BEE), Ministry of Power") was
  misclassified as Tier 3. Caught by running the actual full assessment,
  not by the unit tests alone (which had only exercised short, exact
  authority strings).
