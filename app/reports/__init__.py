"""Report generation: assembles a `app.compliance.engine.ComplianceAssessment`
into the 13-section management report.

- `scoring.py` -- the configurable, category-weighted (Carbon/Energy/
  Evidence/Data Quality) readiness score, transparent by construction
  (metric, weight, score, reason).
- `kpi_dashboard.py` -- the plant's headline operational KPIs for the
  period, each carrying its own data-quality status.
- `models.py` -- the `ComplianceReport` dataclass shape (one field per
  section).
- `report_generator.py` -- `generate_compliance_report(plant, period)`,
  the assembly entry point.
- `renderers.py` -- JSON, Markdown, and PDF export of a `ComplianceReport`.

Output written to `app/reports/generated/`.
"""
