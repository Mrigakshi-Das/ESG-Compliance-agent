"""Compliance domain logic: which requirements apply (requirements.py,
context.py), how gaps are found and explained (gap_analysis.py,
data_quality.py), how they're prioritized (prioritization.py), and what
corrective actions follow (recommendations.py). engine.py composes all of
these into one `run_compliance_assessment(plant, period)` call.

This is business/domain logic, distinct from raw arithmetic
(`app.calculations`) and from orchestration (`app.agent`, which calls
`engine.run_compliance_assessment` for its full-assessment and
root-cause-investigation intents).
"""
