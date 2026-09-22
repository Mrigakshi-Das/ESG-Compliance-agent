"""Regulatory knowledge base, one module per authority (bee.py, sebi.py,
environmental.py), each loading structured, sourced JSON records from
`app/regulations/sources/` into the shared `RegulatoryRequirement` schema
(schema.py). `is_potentially_outdated()` flags stale entries by date, not
LLM judgment. Implemented in Phase 4."""
