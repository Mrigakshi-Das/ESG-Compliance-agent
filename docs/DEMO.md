# End-to-End Demonstration

This is a real, captured run of the system — not a scripted transcript.
Every value below came from actually executing:

```python
from app.agent.orchestrator import run
state = run("Why is Plant B's ESG compliance readiness low, and what should management address first?")
```

against the deterministic synthetic dataset (`app/data/seed_csv/`, regenerable
byte-for-byte with `python -m app.data.generate_synthetic_data`). Reproduce
it yourself with:

```bash
python -m app.data.generate_synthetic_data
python -c "from app.agent.orchestrator import run, render_activity_trace; s = run(\"Why is Plant B's ESG compliance readiness low, and what should management address first?\"); [print(e) for e in render_activity_trace(s)]; print(s.final_answer)"
```

or ask it through the running UI (see [SETUP.md](SETUP.md)) — type the exact
question into **Ask the Agent**.

The trace below shows only the agent's decision-level activity — which tool
ran, what it returned, what was decided next — never a hidden internal
chain-of-thought. This is what `render_activity_trace(state)` returns and
what the control-tower UI's "Agent Activity" console displays live.

---

## Flow overview

```
USER OBJECTIVE
      |
      v
AGENT PLAN
      |
      v
TOOL SELECTION
      |
      v
TOOL EXECUTION
      |
      v
DATA ANALYSIS
      |
      v
GAP IDENTIFICATION
      |
      v
ROOT-CAUSE INVESTIGATION
      |
      v
PRIORITIZATION
      |
      v
RECOMMENDATION
      |
      v
FINAL REPORT
```

---

## 1. USER OBJECTIVE

**Input:** `"Why is Plant B's ESG compliance readiness low, and what should management address first?"`

`app.agent.planner.parse_objective` turns this into a structured `Objective`.
Nothing here is invented — every field is either extracted from the text or
recorded as an explicit assumption:

```json
{
  "raw_query": "Why is Plant B's ESG compliance readiness low, and what should management address first?",
  "plant": "Plant B",
  "mentioned_plants": ["Plant B"],
  "reporting_period": "FY2025-26 Q4",
  "esg_category": "esg_overall",
  "desired_output": "Assess Plant B's ESG compliance readiness",
  "intent": "full_assessment",
  "assumptions": [
    "No reporting period stated; assumed the most recent configured period (FY2025-26 Q4)."
  ]
}
```

`"readiness"` matches `_ASSESSMENT_WORDS`, so the request is classified
`full_assessment` — the broadest intent, which produces the full 13-section
report rather than a single-metric answer. The unstated reporting period is
never silently defaulted without a trace: it's logged as an assumption the
user can see.

## 2. AGENT PLAN

`app.agent.planner.build_plan` looks up the fixed step list and tool set for
`full_assessment` — the plan is a function of the *classified intent*, not
of this specific plant or wording (a `single_metric_emission` query gets a
3-tool plan; `full_assessment` gets this 9-tool plan):

```
1. Identify applicable carbon, energy, and disclosure requirements.
2. Retrieve Plant B's production, emissions, and energy data.
3. Search Plant B's evidence/document repository.
4. Calculate emission intensity and energy intensity.
5. Assess evidence coverage against the required document types.
6. Compare calculated intensity against the configured target, where one is available.
```

Activity trace:
```
[✓] plan_created: Plan created (full_assessment): 9 tool(s) selected
```

## 3. TOOL SELECTION

The 9 tools this plan declares:

```
search_regulations, get_production_data, get_emission_data, get_energy_data,
search_documents, calculate_emission_intensity, calculate_energy_intensity,
assess_evidence, compare_with_target
```

This is a genuine selection, not a fixed script — `search_documents` and
`assess_evidence` only appear because this intent needs evidence coverage;
a plain "what's Plant B's emission intensity" question never touches them
(see the `single_metric_emission` example in the test suite, which selects
only 3 tools).

## 4. TOOL EXECUTION

`_execute_full_assessment` delegates the 9-tool plan to
`app.compliance.engine.run_compliance_assessment`, which calls each tool
directly, once per applicable requirement, rather than the orchestrator
replaying every call itself (see the docstring on `_execute_full_assessment`
in `app/agent/orchestrator.py` for why: composing many tools per requirement
is the compliance engine's job, and its own full internal detail — every
call, every result — is preserved on the returned `ComplianceAssessment`
object, not discarded).

What actually ran underneath, for Plant B / FY2025-26 Q4:
- `search_regulations` — all 10 Phase 4 knowledge-base requirements (BEE PAT ×3, BEE CCTS ×3, SEBI BRSR/BRSR Core ×4)
- `get_production_data`, `get_emission_data`, `get_energy_data` — one call each
- `search_documents` — Plant B's 7-document evidence repository
- `assess_evidence` — once per requirement with a matchable evidence type
- `calculate_emission_intensity`, `calculate_energy_intensity`, `compare_with_target` — for the two metrics with a configured illustrative target

Activity trace:
```
[✓] data_validated: Data quality for Plant B/FY2025-26 Q4: Clean (missing: none, conflicting: none).
```

Data quality is checked *before* anything downstream runs — for Plant B in
this period, every domain came back clean. (Plant C's known missing
production quarter would instead produce a `⚠` here and skip the dependent
calculation — see [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) for how the
system behaves when data isn't clean.)

## 5. DATA ANALYSIS

Deterministic calculations and requirement-status classification run next.
Ten Facts came out of this stage, each one a plain retrieved-or-computed
number, never inferred:

```
BEE-PAT-001:        Human Review Required
BEE-PAT-002:        Human Review Required
BEE-PAT-003:        Human Review Required
BEE-CCTS-001:       Human Review Required
BEE-CCTS-002:       Human Review Required
BEE-CCTS-003:       Human Review Required
SEBI-BRSR-001:      Compliant
SEBI-BRSRCORE-001:  Evidence Missing
SEBI-BRSRCORE-002:  Potential Gap
SEBI-BRSRCORE-003:  Human Review Required
```

The six PAT/CCTS items are `Human Review Required` on principle, not by
data gap: this prototype has no real BEE/MoEFCC gazette list to confirm
Plant B is a named Designated Consumer or Obligated Entity, so the system
refuses to guess either way. Two independent, clearly-labeled assumptions
back the BRSR/BRSR Core rows (documented in `app/compliance/context.py`) —
they apply identically to all three demo plants, and are shown to the user
as assumptions, not facts.

Alongside the regulatory statuses, an **operational benchmark check**
(independent of the legal-applicability question above) flags two metrics
against Plant B's own illustrative internal targets:

```
Fact: Plant B's emission_intensity_tco2e_per_t_cement increased 7.2% across the configured periods.
Fact: Plant B's specific_thermal_energy_consumption_gj_per_t_clinker increased 9.9% across the configured periods.
Fact: Plant B's specific_electricity_consumption_kwh_per_t_cement increased 3.1% across the configured periods.
Fact: Plant B's fuel_consumption_tonnes increased 6.8% across the configured periods.
Fact: Plant B's alternative_fuel_thermal_substitution_pct decreased 20.0% across the configured periods.
Fact: Plant B's clinker_production_tonnes decreased 4.9% across the configured periods.
```

## 6. GAP IDENTIFICATION

```
[⚠] gap_identified: Gap analysis: 11 gap(s) found across 10 applicable requirement(s).
```

11 gaps from 10 requirements because one requirement
(`SEBI-BRSRCORE-002`) additionally spawned an evidence-specific note, and
the two operational-benchmark checks each add their own
`INTERNAL-<METRIC>` gap record alongside the regulatory ones. The top gap:

```json
{
  "requirement_id": "INTERNAL-EMISSION_INTENSITY_TCO2E_PER_T_CEMENT",
  "regulation": "Internal ESG performance benchmark (illustrative -- not a regulatory determination)",
  "status": "Potential Gap",
  "metric": "emission_intensity_tco2e_per_t_cement",
  "actual_value": 0.9773,
  "target_value": 0.78,
  "target_is_illustrative": true,
  "variance_pct": 25.29,
  "notes": ["Benchmarked against an illustrative internal target (0.78), not a confirmed regulatory obligation -- the corresponding regulatory item is Human Review Required pending applicability confirmation (see BEE-CCTS-002 / BEE-PAT-002)."]
}
```

Note the explicit disclosure in `notes`: this gap is real and quantified,
but it is *not* the same claim as "Plant B is non-compliant with CCTS" —
that legal question is still Human Review Required. The system never
conflates the two.

## 7. ROOT-CAUSE INVESTIGATION

```
[✓] root_cause_investigated: Root-cause investigation run for emission_intensity_tco2e_per_t_cement (INTERNAL-EMISSION_INTENSITY_TCO2E_PER_T_CEMENT).
[✓] root_cause_investigated: Root-cause investigation run for specific_thermal_energy_consumption_gj_per_t_clinker (INTERNAL-SPECIFIC_THERMAL_ENERGY_CONSUMPTION_GJ_PER_T_CLINKER).
```

`investigate_root_cause` walks the production → electricity → thermal
energy → fuel → maintenance driver chain. Six measured changes come back as
`Fact` (High confidence — they're direct calculations); two candidate
explanations come back as `Hypothesis` (Medium confidence — inferred
connections, worded as "may," never asserted as certain):

```
Hypothesis (Medium confidence): Part of the rise in emission_intensity_tco2e_per_t_cement
may reflect lower production volume over the period (fixed and semi-fixed
emissions/energy spread over less output) rather than a change in process
efficiency.

Hypothesis (Medium confidence): The increase in specific_thermal_energy_consumption_gj_per_t_clinker
may be related to an unaddressed maintenance issue: 'Kiln Refractory Lining'
has been Overdue since 2025-06-15 (Refractory wear accelerating; relining
inspection deferred twice due to production schedule pressure -- contributing
to rising kiln thermal energy consumption).
```

The maintenance link is traceable to a real record in
`app/data/seed_csv/maintenance.csv` (documented as data-quality issue #9 in
[KNOWN_DATA_ISSUES.md](../app/data/KNOWN_DATA_ISSUES.md)) — the hypothesis
is grounded in an actual overdue work order, not invented.

## 8. PRIORITIZATION

`prioritize_gaps` scores every gap by Risk × Business Impact × Urgency into
a banded priority. The emission-intensity gap comes out **Critical**
(score 100.0); the thermal-energy gap comes out **High**. Both gaps are
attached to real, grounded, non-guessed impact estimates:

```json
"basis": "Estimate: if specific_thermal_energy_consumption_gj_per_t_clinker
were restored to this plant's own best observed value in the configured
history (3.550 vs. the current 3.900), scaled against the current period's
actual energy/emissions. Illustrative, based on this plant's own historical
variation -- not a guaranteed outcome.",
"potential_energy_savings_gj_estimate": 68600.0,
"potential_emission_reduction_tco2e_estimate": 17150.0,
"potential_cost_impact": "Not estimated -- no energy/fuel cost data is configured in this system."
```

Note the last line: where the system has no basis for a number (fuel/energy
cost), it says so explicitly rather than inventing a rupee figure.

## 9. RECOMMENDATION

```
[✓] recommendation_built: Built 11 corrective-action recommendation(s), prioritized.
```

The top recommendation, in full:

| Field | Value |
|---|---|
| Gap | INTERNAL-EMISSION_INTENSITY_TCO2E_PER_T_CEMENT: Potential Gap |
| Priority | **Critical** (score 100.0) |
| Corrective action | Investigate and address the operational driver(s) behind the emission_intensity_tco2e_per_t_cement gap (see root cause) and re-verify after the next full reporting cycle. |
| Suggested owner | Plant Energy/Environment Manager |
| Suggested timeline | Within 30 days |
| Closure evidence | A subsequent period's emission_intensity_tco2e_per_t_cement calculation showing the value back within target, retained with its source data. |

## 10. FINAL REPORT

```
[✓] report_generated: Assembled the 13-section management report.
```

`generate_compliance_report` assembles the full `ComplianceReport`:

- **Overall readiness score: 66.6 / 100** (category-weighted: Carbon 30% /
  Energy 25% / Evidence 25% / Data Quality 20%)
- **11 key gaps**, **2 root-cause investigations**, **6 cited regulatory
  sources**
- Exportable as JSON, Markdown, or PDF (`render_json` / `render_markdown` /
  `render_pdf`, or the **Download Full Report (PDF)** button in the UI)

**Final answer returned to the user:**

> ESG compliance readiness assessment for Plant B (FY2025-26 Q4): overall
> readiness score 66.6/100. Top priority (Critical):
> INTERNAL-EMISSION_INTENSITY_TCO2E_PER_T_CEMENT (Internal ESG performance
> benchmark (illustrative -- not a regulatory determination)): Potential Gap
> -- Investigate and address the operational driver(s) behind the
> emission_intensity_tco2e_per_t_cement gap (see root cause) and re-verify
> after the next full reporting cycle.

**Decision metadata** (the DECIDE step, `_finalize`):

```
confidence: Medium
human_review_required: True
human_review_reasons:
  - Evidence gaps were identified that require human judgment to close.
  - Regulatory applicability could not be determined from available facts and requires human confirmation.
status: completed
```

The agent doesn't just answer — it tells the reader *how much to trust the
answer* and *exactly what a human still needs to check*, which is the
difference between this and a chatbot summarizing a document.

## 11. GUARDRAILS (Phase 12)

Every step above ran through the enterprise guardrail layer
(`app.guardrails`, see [GUARDRAILS.md](GUARDRAILS.md)) — it just didn't
need to block anything to let this real finding through. The same run's
guardrail event log (real output, not illustrative):

```
[✓] guardrail_check: Guardrail: verified regulatory source and version status for 10 applicable requirement(s).
[⚠] guardrail_check: Guardrail: 8 event(s) recorded this run (5 high/critical).
```

The **Guardrails & Reliability** panel for this exact run:

```
HUMAN REVIEW: YES
Data Integrity            100%
Evidence Coverage          25%
Regulatory Source Validity 50%
Calculation Validation    100%

Recent Guardrail Events (8)
  EVIDENCE_MISSING     SEBI-BRSRCORE-003 evidence
  EVIDENCE_MISSING     SEBI-BRSRCORE-002 evidence
  EVIDENCE_MISSING     SEBI-BRSRCORE-001 evidence
  REGULATION_OUTDATED  Superseded/amended by 'SEBI-BRSR-EASE-2025 (28 Mar 2025)'.
  REGULATION_OUTDATED  Superseded/amended by 'SEBI-BRSR-EASE-2025 (28 Mar 2025) -- amends related
                       value-chain/assurance provisions; see SEBI-BRSRCORE-003'.
  REGULATION_OUTDATED  Superseded/amended by 'MOEFCC-GEI-FINAL-2025 (G.S.R. 739(E), 8 Oct 2025);
                       further amended 13 Jan 2026 -- see source registry'.  (x3)
```

The `REGULATION_OUTDATED` findings are not fabricated for this demo — they
come from `superseded_or_amended_by` fields that were already present in
the sourced Phase 4 knowledge base (real, cited amendments to BRSR and the
GHG Emission Intensity rules) but that nothing in the system acted on
before this phase. Guardrail #4 is the first thing to actually read and
use that fact.

### Three more guardrail scenarios, on the same dataset

**DATA_CONFLICT** — asking about Plant C's known conflicting production
record instead of Plant B's clean one:

> Query: `"What is Plant C's production for FY2025-26 Q2?"`
> ```json
> {
>   "status": "DATA_CONFLICT", "metric": "production", "period": "FY2025-26 Q2",
>   "values": [
>     {"value": {"cement_production_tonnes": 181500.0, "...": "..."}, "source": "SAP_PP"},
>     {"value": {"cement_production_tonnes": 179800.0, "...": "..."}, "source": "ESG_Portal"}
>   ],
>   "impact": "production cannot be reliably used in downstream calculations while sources disagree.",
>   "action": "Human verification required"
> }
> ```
> `human_review_required: True` — the two values are never averaged or silently picked.

**ACTION_REQUIRES_APPROVAL** — asking the agent to actually do something
consequential:

> Query: `"Please submit the regulatory report to CPCB for Plant B."`
> Answer: *"This request is a Level 3 consequential action and requires
> explicit human authorization before it can proceed. The agent has not
> executed it, submitted anything, or modified any source data or
> system."*
> `approval_required: True`, `pending_actions[0].status: "ACTION_REQUIRES_APPROVAL"`

**Legal-compliance qualification** — asking the question guardrail #5
exists for:

> Query: `"Is Plant B legally compliant?"`
> The agent still runs the real assessment (`intent: full_assessment`) and
> answers with the same readiness-score/Potential-Gap language as above —
> never a bare "yes" or "no" to a legal question.

See [docs/guardrails test scenarios](../app/tests/test_guardrails_scenarios.py)
for all 15 named scenarios from the Phase 12 brief, run as executable
assertions against this exact dataset.

---

## Additional demonstrations

The same `run()` entry point handles qualitatively different requests with
a genuinely different plan and tool set each time — not five variations on
one template:

| Query | Intent | Tools called |
|---|---|---|
| `"Calculate Plant A's emission intensity."` | `single_metric_emission` | `get_emission_data`, `get_production_data`, `calculate_emission_intensity` |
| `"What is Plant B's specific thermal energy consumption?"` | `single_metric_energy` | `get_energy_data` (reports the metric actually asked for — see the fix in [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)) |
| `"Compare plants on emission intensity for FY2025-26 Q4."` | `cross_plant_comparison` | `compare_plants` |
| `"Why did Plant B's carbon intensity increase?"` | `root_cause_investigation` | `investigate_root_cause` |
| `"Audit Plant B's evidence readiness."` | `evidence_audit` | `search_regulations`, `search_documents`, `assess_evidence` |
| `"What does BRSR Core require?"` | `regulatory_lookup` | `search_regulations` only — never touches plant data |

All of these are exercised as executable assertions in
`app/tests/test_agent_orchestrator.py`, not just prose claims — see
[TEST_RESULTS.md](TEST_RESULTS.md).
