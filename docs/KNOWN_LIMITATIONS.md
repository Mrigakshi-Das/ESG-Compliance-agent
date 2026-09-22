# Known Limitations

Organized by cause, not severity — some of these are permanent properties
of a synthetic-data prototype, others are scope cuts that a real deployment
would need to address first.

## Inherent to a synthetic-data prototype

- **No real company/ownership model.** BRSR/BRSR Core applicability depends
  on which listed entity owns a plant and that entity's market
  capitalization. The synthetic dataset has no company/ownership dimension
  at all, so this is handled as one explicit, uniformly-applied assumption
  (`app/compliance/context.py`'s `DEMO_KNOWN_FACTS`), shown to every user as
  an Assumption finding — never presented as a verified fact. Point this
  system at a real ownership registry and this assumption is removed
  outright, not adjusted.
- **No real BEE/MoEFCC gazette list.** PAT Designated Consumer status and
  CCTS Obligated Entity status require a name match against an authoritative
  government list this prototype does not have and cannot fabricate. Every
  demo plant correctly resolves to `Human Review Required` for all 6
  PAT/CCTS requirements — this is the system behaving *correctly under
  uncertainty*, not a bug to eventually fix with better data.
- **No energy/fuel cost data.** Every business-impact estimate reports
  potential energy savings and emission reductions in physical units (GJ,
  tCO2e) but explicitly declines to convert to a rupee figure — "Not
  estimated — no energy/fuel cost data is configured in this system" — since
  fabricating a cost from an unconfigured price would violate the
  never-invent-a-number principle. Point this system at real fuel/energy
  pricing and it can be added as one more input to `_estimate_business_impact`.
- **Only 3 plants, 10 KB requirements.** Realistic enough to demonstrate the
  architecture; not large enough to stress-test performance at scale (see
  Roadmap).

## Scope cuts made this phase

- **No automated scenario scorecard.** The original brief called for an
  8-dimension scored evaluation harness across 10+ named scenarios.
  `app/evaluation/evaluation_metrics/scorecard.py` is a documented
  `NotImplementedError` stub rather than a half-built approximation — see
  [TEST_RESULTS.md](TEST_RESULTS.md) for why the 450-test pytest suite
  already covers the same 8 dimensions as executable assertions, just not
  packaged as a standalone scored report.
- **Water and waste are not scored.** `get_water_data`/`get_waste_data`
  tools exist and are tested, and both domains have known data-quality
  issues seeded into them, but neither has regulatory requirement records
  or a category weight in the readiness score yet — they were kept as
  "post-MVP, architecture-ready" per the original scope decision. Adding
  them is a data/config change (new KB records + a category weight), not a
  code change (see [architecture.md](architecture.md) §5).
- **Single reporting period per query.** The agent answers about one
  plant/period at a time (or a cross-plant comparison for one period); there
  is no multi-period trend dashboard beyond what `investigate_root_cause`'s
  own driver-chain walk surfaces.

## Fixed during this phase's final-polish review

Documented here rather than silently dropped, since a reader auditing this
system should be able to see what was wrong before and verify it's actually
fixed now:

- **Evidence-audit intent used unmatchable text.** `_execute_evidence_audit`
  in `app/agent/orchestrator.py` used to build its required-evidence-types
  list from the regulatory knowledge base's long, human-readable citation
  text (e.g. *"GHG Verification Statement / accredited carbon verification
  agency report"*), which can never substring-match a real document's short
  `document_type` value — every evidence audit reported everything
  "Missing" regardless of what was actually on file. Fixed by sharing
  `app.compliance.engine.REQUIREMENT_EVIDENCE_TYPES` (the same short-label
  mapping the full compliance assessment already used correctly) between
  both call sites. Covered by a regression test in `test_agent_orchestrator.py`.
- **Thermal-energy questions got an electrical-energy answer.**
  `_execute_single_metric_energy` is reached by any query mentioning
  "energy," "electricity," or "thermal" (`planner.py`'s `_ENERGY_WORDS`),
  but used to always compute and report electrical energy intensity — a
  user asking specifically about thermal/specific energy consumption got an
  electrical-intensity number with no indication thermal wasn't computed.
  Fixed by branching on `infer_metric_key` so a thermal-specific or
  electricity-specific query gets the metric it actually asked for. Covered
  by 3 regression tests.
- **"Key Gaps" panel showed recommendations, not gaps.** The control-tower
  UI's Key Gaps table (`app/ui/static/app.js`) was rendering
  `priority_actions` (the corrective-action recommendations) instead of
  `key_gaps` (the actual per-requirement `Gap` objects with real compliance
  statuses like "Potential Gap" / "Evidence Missing") — so it duplicated the
  Corrective Actions table below it almost exactly, and its "Severity"
  column showed a recommendation's priority band, never the underlying
  compliance status. Fixed to render real `Gap` data with a Requirement /
  Status / Metric / Priority / Notes layout; verified live in the browser.
- **`/api/report.pdf` had no error handling.** Unlike `/api/run`, a PDF
  rendering failure would have surfaced a raw Flask traceback to the client
  instead of a clean JSON error. Fixed to match `/api/run`'s pattern.
- **Two unused function parameters.** `get_applicable_requirements` accepted
  `esg_category` and `reporting_period` parameters that were never read in
  the function body (and no caller passed the first, while every caller
  passed the second to no effect). Removed both — `plant` remains an
  intentional, tested no-op (see the docstring and
  `test_same_result_for_every_plant`), since the demo's applicability facts
  genuinely apply uniformly across all three plants.
- **Stale cross-reference in the regulatory knowledge base.** A note field
  in `app/regulations/sources/sebi.json` pointed to
  `app/regulations/plant_context.py`, a module that was renamed to
  `app/compliance/context.py` in an earlier phase and never updated in this
  comment. Corrected.

## Guardrail layer limitations (Phase 12)

See [GUARDRAILS.md](GUARDRAILS.md) for the full architecture; these are the
specific, honest gaps in it:

- **Guardrail #10 (action authorization) has no real action to gate yet.**
  This system has never sent an email, filed a report, or written to a
  source system — there is no Level 3 capability to actually block, only
  the *request* for one, which the `external_action_request` intent
  correctly refuses and explains. The guardrail exists so the check is
  already in place the moment such a capability is added (see
  [ROADMAP.md](ROADMAP.md)), not because it's protecting something real
  today.
- **Source-tier classification is keyword/substring-based**, matching this
  project's existing rule-based style everywhere else. A source phrased
  very differently from the examples in `app/guardrails/
  source_validation.py` could be misclassified. This was caught once
  already during this phase's own testing — the initial version required
  an *exact* match against a short authority name and misclassified every
  real BEE/SEBI source (whose `authority` field reads e.g. "Bureau of
  Energy Efficiency (BEE), Ministry of Power") as Tier 3 until fixed and
  re-verified against the live full assessment, not just unit tests.
- **The data-quality score's "timeliness" sub-score is a heuristic**
  (count of flagged issues), not a measurement against a live ingestion
  timestamp — this prototype has none to measure against.
- **Output validation's legal-compliance check is phrase-based.** It
  catches the phrasings this phase's test scenarios and the guardrail
  brief's own examples use ("is the plant legally compliant," "fully
  compliant with the law," ...), not every conceivable way to ask the same
  question. A genuinely different phrasing could slip through without
  triggering the qualification check — the underlying report-level
  disclaimer (`app.reports.report_generator`'s fixed
  "not a determination of legal compliance" text) remains the backstop
  either way.
- **Regulatory version checks run per full-assessment, not continuously.**
  A requirement's `superseded_or_amended_by`/`last_reviewed` fields are
  only checked when `_execute_full_assessment` runs — there's no
  background job that would surface a newly-outdated requirement between
  queries.

## What was checked and found *not* to be a problem

- `app/agent/llm_client.py` is real, tested code (a genuine Claude tool-use
  loop with turn dispatch and a max-turn safety cap), not orphaned cruft —
  it's simply inactive whenever `ANTHROPIC_API_KEY` is unset, which is every
  test run and this demonstration.
- Regulatory applicability logic was specifically audited for overstated
  certainty and found consistent: PAT/CCTS never resolve to a false
  "Applicable," every KB record carries a source/confidence/last-reviewed
  date, and staleness is a plain date check rather than an LLM judgment.
