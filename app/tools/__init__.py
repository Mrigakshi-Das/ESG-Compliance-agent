"""Agent-callable tools, one module per domain (production, energy,
emissions, water, waste, documents, regulations, maintenance, evidence).
Each is a thin, swappable adapter over `app.data` / `app.regulations` that
adds data-quality validation before returning to the agent. No tool
generates or guesses a value -- everything returned is retrieved or flagged
missing. Also includes analytics.py (get_historical_metric, compare_plants)
and metrics.py (the shared metric registry both use)."""
