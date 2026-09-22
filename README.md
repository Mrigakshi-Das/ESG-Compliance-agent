# Cement ESG & Regulatory Compliance Agent

An autonomous AI agent that assesses ESG and regulatory compliance readiness
for cement manufacturing plants — given a natural-language objective, it
independently plans a sequence of sub-tasks, selects and calls the tools it
needs, runs deterministic calculations, identifies compliance gaps,
investigates root causes, prioritizes issues by risk and business impact,
and produces a structured, management-ready report.

**This is not a chatbot.** See
[docs/AI_AGENT_QUALIFICATION.md](docs/AI_AGENT_QUALIFICATION.md) for exactly
what makes it an agent — autonomy, planning, tool use, state, decision-level
reasoning, a feedback loop, and error handling — each claim pointing at the
actual code and test that backs it.

> **Compliance disclaimer:** This system produces a *compliance readiness
> assessment based on the configured regulatory knowledge base*. It does not
> determine legal compliance.

## Quick start

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python -m app.data.generate_synthetic_data
python -m pytest -q
python -m app.ui.app          # http://127.0.0.1:5057
```

Full steps and troubleshooting: [docs/SETUP.md](docs/SETUP.md).

## See it work

```
"Why is Plant B's ESG compliance readiness low, and what should management address first?"
```

[docs/DEMO.md](docs/DEMO.md) walks through a real, captured run of this
exact question end to end — objective → plan → tool selection → tool
execution → data analysis → gap identification → root-cause investigation →
prioritization → recommendation → final report — showing the agent's
decision trace at every stage, never a hidden chain-of-thought.

## Documentation

| Document | Covers |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Component diagram, data flow, tech-choice rationale, extensibility points |
| [docs/DEMO.md](docs/DEMO.md) | The full worked end-to-end demonstration |
| [docs/SETUP.md](docs/SETUP.md) | Install, data generation, running tests and the UI |
| [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md) | Current test count and coverage by area |
| [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) | What's inherent to the prototype, what was scoped out, what was found and fixed |
| [docs/ROADMAP.md](docs/ROADMAP.md) | What extends this architecture next, roughly nearest-first |
| [docs/AI_AGENT_QUALIFICATION.md](docs/AI_AGENT_QUALIFICATION.md) | Why this is an agent, not an LLM wrapper |
| [docs/GUARDRAILS.md](docs/GUARDRAILS.md) | The enterprise guardrail layer — 14 guardrails, architecture, what backed each one before this phase |
| [docs/BUSINESS_CASE.md](docs/BUSINESS_CASE.md) | Problem statement, current/future-state workflows, persona value, business impact, success metrics |
| [docs/presentation.html](docs/presentation.html) | The 2-5 page presentation story — problem → solution → live demo → business value → future scope |
| [app/data/DATA_DICTIONARY.md](app/data/DATA_DICTIONARY.md) | Every synthetic-data field, unit, and source |
| [app/data/KNOWN_DATA_ISSUES.md](app/data/KNOWN_DATA_ISSUES.md) | The 9 deliberate data-quality issues seeded into the dataset |
| [app/regulations/PHASE4_SOURCES.md](app/regulations/PHASE4_SOURCES.md) | How each regulatory fact was sourced and verified |

## Scope

Four ESG areas, with the architecture designed to extend to more without
rework (see [docs/ROADMAP.md](docs/ROADMAP.md)):

1. Carbon / GHG emissions (Scope 1, Scope 2, emission intensity)
2. Energy consumption (specific thermal/electrical energy consumption)
3. Regulatory compliance readiness (BEE PAT/CCTS, SEBI BRSR/BRSR Core)
4. ESG evidence / document readiness (audit trail, calibration, reporting)

Water and waste tools and synthetic data exist from an early phase onward,
but are not yet scored regulatory categories — see
[docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md).

## Project structure

```
cement-esg-agent/
├── README.md
├── requirements.txt
├── docs/                    architecture, demo, setup, test results, limitations, roadmap, AI-agent qualification
├── app/
│   ├── agent/                orchestration -- OBSERVE->PLAN->ACT->OBSERVE->ANALYZE->DECIDE->REPORT
│   │   ├── orchestrator.py     run(): the single entry point
│   │   ├── planner.py          objective parsing, intent classification, dynamic tool selection
│   │   ├── llm_client.py       optional Claude tool-use loop (used only if ANTHROPIC_API_KEY is set)
│   │   └── state.py            AgentRunState / ActivityEntry / Objective
│   ├── tools/                 17 agent-callable tools, one module per domain (registry.py has the full inventory)
│   ├── calculations/          deterministic math -- emission/energy intensity, target comparison, priority scoring
│   ├── compliance/            applicability, gap analysis + root cause, prioritization, recommendations, engine
│   ├── data/                  synthetic CSV -> SQLite backend behind PlantDataSource/DocumentSource interfaces
│   ├── regulations/            regulatory knowledge base, one module per authority (BEE, SEBI)
│   ├── reports/                13-section report assembly + JSON/Markdown/PDF renderers
│   ├── evaluation/             evaluation scorecard (documented stub -- see docs/KNOWN_LIMITATIONS.md)
│   ├── ui/                     Flask API + hand-built control-tower frontend
│   ├── guardrails/              enterprise guardrail engine -- data integrity, source/regulatory validation, calculation safety, evidence, confidence, action authorization (docs/GUARDRAILS.md)
│   └── tests/                  450 tests (see docs/TEST_RESULTS.md)
```

## Tech stack

| Concern | Choice | Why |
|---|---|---|
| Structured plant data | SQLite, seeded from CSV, behind swappable interfaces | Zero-setup but has real schema/query semantics; drop-in for a real DB/API later |
| Regulatory knowledge base | Versioned JSON records, one loader per authority | Structured fields (not prose) mean staleness/sourcing checks are plain code, never an LLM judgment |
| Calculations & compliance logic | Pure, deterministic Python | Numbers must be reproducible and auditable, never LLM-generated |
| Agent orchestration | Rule-based planner by default; optional real Claude tool-use loop | Fully testable and reproducible with no network access; the LLM path (when enabled) never computes a number |
| UI | Flask API + hand-built static frontend | Full control over an ESG/manufacturing "control tower" look — the brief explicitly rules out a generic chatbot UI |
| Testing | pytest (450 tests) | See [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md) |
| Guardrails | `app/guardrails` -- a dedicated, reusable engine, not scattered if/else | See [docs/GUARDRAILS.md](docs/GUARDRAILS.md) |

Full rationale: [docs/architecture.md](docs/architecture.md) §4.

## Implementation principles

1. Calculations are deterministic Python, never LLM-generated numbers.
2. The agent never invents plant data or regulatory requirements — both come
   only from `app/data` and `app/regulations/sources`.
3. Every regulatory claim carries a source document, version/source date,
   and last-reviewed date; stale entries are flagged automatically.
4. Every finding is labeled Fact, Calculation, Assumption, or Hypothesis so
   a reader can tell which is which — a Hypothesis is never presented with
   the confidence of a Fact.
5. Regulatory applicability that cannot be confirmed from available facts
   resolves to `Human Review Required`, never a guessed pass or fail.
6. All data tools are thin adapters over `app/data`, so they can later be
   pointed at SAP, IoT/CEMS feeds, ESG databases, or document repositories
   without changing the agent or calculation logic.
7. Every consequential/external action (submitting a filing, changing an
   operating parameter, modifying source data) requires explicit human
   approval before it executes — the agent can recommend, but never
   silently carries out or implies it carried out a Level 3 action. See
   [docs/GUARDRAILS.md](docs/GUARDRAILS.md).
