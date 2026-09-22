# Architecture

## 1. Design goals

- **Deterministic where it matters.** Every number in this system — an
  emission intensity, a variance against target, a priority score, a
  readiness percentage — comes from a pure Python function. Objective
  parsing and intent classification are also deterministic (keyword/pattern
  rules in `app/agent/planner.py`); no LLM call sits on the critical path of
  any run in this environment.
- **Grounded, not generative.** The agent can only see plant data and
  regulatory requirements that exist in `app/data` and
  `app/regulations/sources`. It cannot fabricate a number or a rule — every
  tool call returns structured data, and every regulatory claim carries a
  source citation.
- **Explainable at the decision level.** Every run produces an "Agent
  Activity" trace — objective understood, plan created, each tool call's
  outcome, gaps found, root causes investigated, recommendations built,
  report generated — without exposing internal chain-of-thought. See
  `app.agent.orchestrator.render_activity_trace`.
- **Honest about uncertainty.** Every finding is labeled Fact, Calculation,
  Assumption, or Hypothesis. Regulatory applicability that cannot be
  confirmed from available facts resolves to `Human Review Required`, never
  a guessed pass or fail.
- **Swap-in ready.** Every tool is a thin adapter over `app/data`. The
  synthetic CSV/SQLite backend can be replaced later by SAP, IoT/CEMS, or an
  ESG database connector without touching the agent, calculations, or UI.
- **Safely autonomous, not restrictively autonomous.** `app/guardrails`
  enforces 14 explicit boundaries (no hallucinated data, no unresolved
  conflicts, no unsupported compliance claims, no unapproved consequential
  action, ...) as a reusable, programmatically checked engine — not prompt
  wording — while still letting the agent independently plan, retrieve,
  calculate, and recommend. See [GUARDRAILS.md](GUARDRAILS.md).

## 2. Component diagram

```mermaid
flowchart TD
    U["User: natural-language objective\n(typed question, or Plant/Period/Type controls)"] --> UILayer

    subgraph UILayer ["app/ui -- Flask API + static control-tower frontend"]
        SRV["server.py\nPOST /api/run, GET /api/report.pdf, GET /api/meta"]
        FE["static/app.js + index.html\nrenders whatever the API returns -- no client-side scoring logic"]
        SRV -.serves.-> FE
    end
    UILayer --> ORCH

    subgraph AgentCore ["app/agent -- orchestration"]
        ORCH["orchestrator.py\nrun(): OBSERVE -> PLAN -> ACT -> OBSERVE -> ANALYZE -> DECIDE -> REPORT"]
        PLANNER["planner.py\nparse_objective + build_plan\n(deterministic keyword/pattern rules)"]
        LLM["llm_client.py\noptional Claude tool-use loop\n(used only if ANTHROPIC_API_KEY is set)"]
        STATE[("state.py\nAgentRunState: plan, tools_called,\nfindings, gaps, activity_trace,\nguardrail_events, confidence_assessment, ...")]
        ORCH --> PLANNER
        ORCH -. "if ANTHROPIC_API_KEY set" .-> LLM
        PLANNER -. writes .-> STATE
        ORCH -. reads/writes .-> STATE
    end

    subgraph Guardrails ["app/guardrails -- 14 enforced boundaries (GUARDRAILS.md)"]
        GENGINE["engine.py: GuardrailEngine\none per run, attached to state"]
        GDATA["data_integrity.py + calculation_safety.py\nDATA_OK/MISSING/CONFLICT/ANOMALY,\nstructured CalculationResult"]
        GREG["source_validation.py + regulatory_validation.py\nTier 1/2/3, CURRENT/OUTDATED/UNKNOWN"]
        GEVID["evidence_validation.py\nEVIDENCE_* -- 'no evidence != compliant'"]
        GACT["action_authorization.py + stop_conditions.py\nLEVEL_1/2/3, ACTION_REQUIRES_APPROVAL"]
        GOUT["confidence.py + output_validation.py\n5-factor confidence, final-response check"]
        GENGINE --> GDATA & GREG & GEVID & GACT & GOUT
    end

    ORCH -. "every _call_tool result" .-> GENGINE
    GENGINE -. "events, confidence,\npending_actions" .-> STATE

    ORCH -->|"9 of ~10 intents:\ndirect per-tool calls"| Tools
    ORCH -->|"full_assessment /\nroot_cause_investigation intents"| Compliance
    ORCH -->|"external_action_request intent"| Guardrails

    subgraph Tools ["app/tools -- 17 agent-callable tools (TOOL_REGISTRY)"]
        T1["regulations.py: search_regulations"]
        T2["production.py / energy.py / emissions.py\nwater.py / waste.py / fuel_quality.py / weather.py\nmaintenance.py: get_*_data"]
        T3["documents.py: search_documents\nevidence.py: assess_evidence"]
        T4["analytics.py: get_historical_metric, compare_plants"]
        T5["calculations/*.py (registered as tools too):\ncalculate_emission_intensity, calculate_energy_intensity,\ncompare_with_target, calculate_priority"]
    end

    subgraph DataLayer ["app/data -- swappable backend"]
        IFACE[["base.py: PlantDataSource / DocumentSource"]]
        DS["production.py energy.py emissions.py\nwater.py waste.py maintenance.py evidence.py"]
        IFACE -.implemented by.-> DS
        DS --> SEEDCSV[("seed_csv/*.csv -> cement_esg.db\n(deterministic generator, no randomness)")]
    end

    subgraph RegLayer ["app/regulations -- one module per authority"]
        RSCHEMA[["schema.py: RegulatoryRequirement"]]
        RB["bee.py: PAT, CCTS"]
        RS["sebi.py: BRSR, BRSR Core"]
        RE["environmental.py: future norms"]
        APPL["applicability.py: evaluate_requirement\n(explicit conditions, never a guess)"]
        RSCHEMA --- RB & RS & RE
    end

    T2 & T3 --> DataLayer
    T1 --> RegLayer
    RB & RS & RE --> SOURCES[("sources/*.json\nsource + version + last-reviewed date")]

    subgraph Compliance ["app/compliance -- domain logic"]
        REQ["requirements.py\nget_applicable_requirements\n(uses applicability.py + context.py's documented demo assumptions)"]
        DQ["data_quality.py\nassess_data_quality"]
        GAP["gap_analysis.py\nclassify_requirement_status (8 statuses)\n+ investigate_root_cause: driver chain +\nfuel-quality/weather scan + optional LLM stage"]
        PRI["prioritization.py\nRisk x Business Impact x Urgency"]
        REC["recommendations.py\ncorrective actions, grounded impact estimates"]
        ENGINE["engine.py\nrun_compliance_assessment: wires the above,\ncalls Tools directly per requirement"]
        ENGINE --> REQ & DQ & GAP & PRI & REC
    end

    ENGINE -->|calls| Tools
    REQ --> RegLayer

    ORCH -->|full_assessment builds one| Reports

    subgraph Reports ["app/reports -- management report"]
        RG["report_generator.py\ngenerate_compliance_report:\n13-section ComplianceReport"]
        SCORE["scoring.py\ncategory-weighted readiness score\n(Carbon/Energy/Evidence/Data Quality)"]
        REND["renderers.py\nrender_json / render_markdown / render_pdf"]
        RG --> SCORE
        RG --> REND
    end

    Compliance -.ComplianceAssessment.-> Reports
    Compliance -. "per-requirement evidence status,\nregulatory requirement records" .-> GENGINE
    STATE -->|serialized JSON| SRV
    Reports -.attached to state.report.-> STATE
```

## 3. Data flow for one request

Using the worked example `"Why is Plant B's ESG compliance readiness low,
and what should management address first?"` (see [DEMO.md](DEMO.md) for the
full captured trace):

1. **Understand objective** — `parse_objective` extracts plant ("Plant B"),
   reporting period (defaulted, logged as an assumption), ESG category, and
   classifies intent (`full_assessment`, matched on "readiness"). Missing
   fields become explicit, displayed assumptions, never silent defaults.
2. **Plan** — `build_plan` returns the fixed step list and the 9-tool set
   the `full_assessment` intent declares. The plan is a genuine function of
   the classified intent, not a fixed script — a different query produces a
   different plan and a different, shorter tool list (verified by tests
   asserting different objectives yield different `tools_called`).
3. **Select & call tools / Retrieve data** — the `full_assessment` handler
   delegates to `app.compliance.engine.run_compliance_assessment`, which
   calls `search_regulations`, `get_production_data`, `get_emission_data`,
   `get_energy_data`, `search_documents`, and `assess_evidence` per
   applicable requirement — only the tools the plan actually needs.
4. **Validate** — every tool result carries its own `status` (`ok` /
   `missing` / `conflict`); `assess_data_quality` summarizes this per
   plant/period before any calculation runs.
5. **Calculate** — `calculate_emission_intensity` / `calculate_energy_intensity`
   / `compare_with_target` are pure functions in `app/calculations`; a
   missing/conflicting input skips the calculation and logs an unresolved
   question rather than guessing.
6. **Identify gaps** — each applicable requirement gets one of 8 statuses:
   Compliant, Potential Gap, Data Missing, Evidence Missing, Evidence
   Outdated, Data Conflict, Not Applicable, or Human Review Required.
7. **Root cause & prioritize** — `investigate_root_cause` walks the
   production → electricity → thermal energy → fuel → maintenance driver
   chain, then a second, still-deterministic scan across fuel-quality and
   weather data (`_EXTERNAL_FACTOR_CHAIN`) for grounded contributing
   factors outside that original chain, and finally an *optional*
   LLM-assisted stage (only when `ANTHROPIC_API_KEY` is set) that may
   suggest genuinely novel hypotheses — but only ones traceable to Facts
   the deterministic stages already established, never a new invented
   fact. Every stage returns typed `Fact`/`Hypothesis` findings with a
   confidence level; `prioritize_gaps` scores each gap by Risk × Business
   Impact × Urgency into a Critical/High/Medium/Low band.
8. **Recommend** — `build_recommendation` turns each gap into a 9-field
   corrective action (owner, timeline, grounded business-impact estimate,
   closure evidence) — no invented cost figures.
9. **Report** — `generate_compliance_report` assembles the 13-section
   management report; `render_markdown`/`render_json`/`render_pdf` export it.
10. **Decide** — `_finalize` sets confidence and `human_review_required`
    from what actually happened (evidence gaps found? applicability
    unresolved?), and the run's `status`.

## 4. Why these tech choices

- **SQLite over a live DB**: zero-setup, file-based, but has real schema and
  query semantics — closer to a production data source than in-memory
  dicts, and a straightforward swap for a real DB/API connector later. CSVs
  remain the human-editable seed source (`app/data/generate_synthetic_data.py`
  builds the SQLite file from them); nothing in the generator is randomized,
  so regenerating reproduces the dataset exactly.
- **JSON regulatory records over free text**: keeps every requirement
  structured (authority, metric, threshold, evidence, source,
  version/review dates) so the agent reasons over fields instead of parsing
  prose, and "flag outdated regulation" is a plain date check
  (`is_potentially_outdated()`), never an LLM judgment.
- **Deterministic planning, LLM at the edges only**: `app/agent/planner.py`'s
  rule-based classifier is what every test and the demo run on — it needs no
  network access and is fully reproducible. `app/agent/llm_client.py`
  implements a real Claude tool-use agentic loop as an *optional*
  alternative (auto-enabled only if `ANTHROPIC_API_KEY` is set); its control
  flow is tested against a scripted fake client. Either path, calculations
  and compliance rules are identical — the LLM (when used) never computes a
  number or invents a fact.
- **Flask + hand-built static frontend over Streamlit**: the brief calls for
  something that reads as an ESG/manufacturing control tower, not a generic
  chatbot or a Streamlit component demo. A thin JSON API plus static
  HTML/CSS/JS gives full control over the dark instrumentation theme,
  circular readiness gauge, and Fact/Hypothesis root-cause flow for
  negligible extra cost over Streamlit.

## 5. Extensibility points

| Later addition | Where it plugs in |
|---|---|
| Real CEMS / IoT feed | Replace the `app/data` repository backing `get_emission_data` / `get_energy_data`; tool signature unchanged |
| SAP production data | Replace the `app/data` repository backing `get_production_data`; tool signature unchanged |
| Document repository (SharePoint, etc.) | Replace `search_documents`'s backing store; tool signature unchanged |
| New regulation (e.g. a state pollution-control norm) | Add a JSON record to `app/regulations/sources/`; no code change needed for `search_regulations` to pick it up |
| Water / waste as first-class scored metrics | `get_water_data` / `get_waste_data` tools already exist; add regulatory records + gap rules + category weight |
| Additional plants | Add rows to the seed CSVs; no code change |
| Automated scenario scoring | `app/evaluation/evaluation_metrics/scorecard.py` is a documented stub (`NotImplementedError`) for the 8-dimension scorecard described in [ROADMAP.md](ROADMAP.md) |
| New ESG domain entirely | Add a `PlantDataSource` subclass in `app/data`, a tool in `app/tools`, a calculation module in `app/calculations`, and requirement records in `app/regulations/sources` — the agent/compliance layers are domain-agnostic |
