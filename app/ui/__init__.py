"""Control-tower web interface: `app.py` is the entry point
(`python -m app.ui.app`), `server.py` is the Flask API, and `static/` is a
hand-built HTML/CSS/JS frontend (no framework) -- dashboard, agent activity
console, key gaps, root-cause flow, corrective actions, and data quality,
all driven by `app.agent.orchestrator.run` through the API. Streamlit was
the Phase 1 plan; Phase 8 needed full layout/visual control to hit the
"control tower, not a chatbot" brief, which a thin API + static frontend
gives more directly.
"""
