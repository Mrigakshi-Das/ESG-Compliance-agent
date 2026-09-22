# Setup

Verified working from a clean checkout as of this writing (Python 3.14,
Windows/PowerShell; the codebase is pure-Python and has no OS-specific
dependencies).

## 1. Install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

See [requirements.txt](../requirements.txt) for exactly what's installed and
why (pandas for the data layer, Flask for the UI, fpdf2 for PDF export,
anthropic only if you enable the optional LLM path, pytest for the test
suite).

## 2. Generate the synthetic dataset

The repository does not ship a pre-built database — generate it once:

```bash
python -m app.data.generate_synthetic_data
python -m app.data.validate_data
```

The generator is fully deterministic (no randomness anywhere): every value
is a fixed, hand-authored driver or a formula over one, so running it again
reproduces `app/data/seed_csv/*.csv` and `app/data/cement_esg.db`
byte-for-byte identically. `validate_data` confirms both the dataset's
structure and the 9 deliberate data-quality issues it's supposed to contain
(see [app/data/KNOWN_DATA_ISSUES.md](../app/data/KNOWN_DATA_ISSUES.md)).

## 3. Run the test suite

```bash
python -m pytest -q
```

All tests should pass — see [TEST_RESULTS.md](TEST_RESULTS.md) for the
current count and what each area covers.

## 4. Run the control-tower UI

```bash
python -m app.ui.app
```

Serves at **http://127.0.0.1:5057**. Open it, pick a plant/period/assessment
type and click **Run Assessment**, or type a question directly into
**Ask the Agent** — see [DEMO.md](DEMO.md) for the worked example query.

No API key is required for any of the above. The agent's deterministic
rule-based planner (`app/agent/planner.py`) handles every intent, every
calculation, and every compliance rule — this is what every test and the
demonstration run on.

## 5. (Optional) Enable the LLM-assisted planner

```bash
# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-..."
python -m app.ui.app
```

When set, `app.agent.llm_client` handles objective parsing and tool
selection through a real Claude tool-use loop instead of the deterministic
planner. This is optional and off by default; calculations and compliance
rules are byte-identical either way — the LLM path (when enabled) never
computes a number or invents a fact, only decides which already-deterministic
tools to call. Its control flow is covered by
`app/tests/test_agent_llm_client.py` against a scripted fake client, so no
API key or network access is needed to verify it works.

## Troubleshooting

- **`ModuleNotFoundError` on any `app.*` import** — run commands from the
  `cement-esg-agent/` directory (the repository root), not from inside
  `app/`.
- **Tests fail after editing `app/data/seed_csv/*.csv` by hand** — re-run
  `python -m app.data.generate_synthetic_data` to rebuild
  `cement_esg.db` from the CSVs, or run `validate_data` to see exactly which
  structural/known-issue check failed.
- **Port 5057 already in use** — another instance of the UI is likely still
  running; stop it, or edit the port in `app/ui/app.py`.
