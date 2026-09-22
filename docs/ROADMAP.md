# Future Roadmap

Ordered roughly by how directly each builds on what already exists, not by
priority — a real deployment's priority would depend on which regulatory
deadline or plant is most at risk, which this prototype can't know.

## Near-term (extends existing architecture, no redesign)

1. **Automated evaluation scorecard.** Build out
   `app/evaluation/evaluation_metrics/scorecard.py`'s two stubbed functions
   (`score_scenario`, `build_scorecard`) against 10+ named scenarios covering
   the 8 dimensions in the original brief (tool-selection accuracy,
   calculation accuracy, regulatory-retrieval accuracy, gap-identification
   accuracy, recommendation quality, data-quality handling, missing-information
   handling, end-to-end completion). The 291-test pytest suite already
   exercises all 8 dimensions as pass/fail assertions; this would turn that
   into a scored, trend-able report instead.
2. **Water and waste as scored ESG categories.** The tools
   (`get_water_data`/`get_waste_data`) and synthetic data already exist. Add
   regulatory requirement records to `app/regulations/sources/`, gap rules
   in `app/compliance/engine.py`'s benchmark table, and a 5th category
   weight in `app/reports/scoring.py`.
3. **Real cost data → real financial impact estimates.** Every business-impact
   estimate currently stops at physical units (GJ, tCO2e) because no
   fuel/energy price is configured. Adding one input (a price table per
   plant/period) to `_estimate_business_impact` in `app/compliance/engine.py`
   turns "Not estimated" into an actual rupee figure, without changing the
   grounded-estimate methodology.
4. **More plants, more periods.** Architecturally free — add rows to the
   seed CSVs (or point `app/data`'s repository classes at a real source).
   Useful for testing at a scale closer to a real cement group's plant
   count.

## Medium-term (new capability, same layering)

5. **Real regulatory applicability data feeds.** The two "Human Review
   Required" categories (PAT/CCTS Designated Consumer status, BRSR/BRSR Core
   company ownership) exist because no gazette list or company registry is
   wired in. Replacing `app.compliance.context.DEMO_KNOWN_FACTS` with a real
   data feed (or a small admin UI to confirm these facts once per plant)
   would let those resolve to genuine `Applicable`/`Not Applicable`
   verdicts instead of a standing Human Review flag — without changing
   `evaluate_requirement`'s logic at all, since it already treats these as
   ordinary input facts.
6. **Multi-period trend dashboards.** `investigate_root_cause` already walks
   a driver chain across history for one metric; a dedicated trends view
   (multiple metrics, multiple periods, on one chart) would give management
   a faster way to spot a Plant-B-style slow degradation before it becomes
   a Critical gap.
7. **Notification / workflow integration.** Corrective-action recommendations
   currently have a suggested owner and timeline but no actual ticketing.
   Wiring `build_recommendation`'s output to an email/Jira/ticketing
   integration would close the loop from "the agent found this" to "someone
   is assigned to fix it."

## Longer-term (real infrastructure swap-in)

8. **Real CEMS/IoT/SAP data connectors.** Every tool in `app/tools` is
   already a thin adapter over a `PlantDataSource`/`DocumentSource`
   interface (`app/data/base.py`) specifically so this swap doesn't touch
   the agent, calculations, or compliance logic — see
   [architecture.md](architecture.md) §5 for exactly which module to
   replace per data source.
9. **Multi-tenant / multi-company deployment.** Today the system assumes one
   company's plants. Supporting multiple companies would mean adding a
   company/tenant dimension to the data layer and the applicability-fact
   model, plus access control in `app/ui/server.py` — a real infrastructure
   project, not a small extension.
10. **LLM-assisted narrative generation, more broadly.** `app.agent.llm_client`
    already demonstrates the pattern (LLM decides which deterministic tool
    to call; never computes a number). Extending it to generate more of the
    report's prose sections (while keeping every number sourced from the
    same deterministic pipeline) would make the output read even more like
    a human-written memo without weakening the never-invent-a-number
    guarantee — the key design constraint any such extension must preserve.
