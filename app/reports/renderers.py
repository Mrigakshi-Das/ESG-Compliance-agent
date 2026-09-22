"""Renders a ComplianceReport to JSON, Markdown, and (best-effort) PDF.

Markdown is the human-readable deliverable: management language, tables
for anything tabular, no generic ESG filler -- every number is the one
already computed by the compliance engine, never restated loosely. JSON is
a straight `dataclasses.asdict` dump for machine consumption (a UI, a
downstream system). PDF uses fpdf2's built-in core font, so text is
sanitized to latin-1 first rather than risking a crash on a stray
character -- acceptable for a management report, which is plain business
English throughout.
"""

import json
from dataclasses import asdict

from app.reports.models import ComplianceReport


def render_json(report: ComplianceReport) -> str:
    return json.dumps(asdict(report), indent=2, default=str)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None._\n"
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(c).replace("\n", " ") for c in row) + " |")
    return "\n".join(lines) + "\n"


def render_markdown(report: ComplianceReport) -> str:
    r = report
    out: list[str] = []
    out.append(f"# ESG & Regulatory Compliance Report -- {r.plant}")
    out.append(f"**Reporting period:** {r.period}  \n**Generated:** {r.generated_at}")
    out.append(f"\n> {r.disclaimer}\n")

    out.append("## 1. Executive Summary")
    out.append(r.executive_summary + "\n")

    out.append("## 2. Overall ESG Readiness Score")
    out.append(f"**{r.readiness_score['overall_score']}/100**\n")
    out.append(_table(
        ["Category", "Weight", "Score", "Reason"],
        [[c.category, f"{c.weight:.0%}", f"{c.score:.1f}", c.reason] for c in r.readiness_score["breakdown"]],
    ))

    out.append("## 3. KPI Dashboard")
    out.append(_table(
        ["KPI", "Value", "Unit", "Target", "Status"],
        [[k.name, k.value if k.value is not None else "N/A", k.unit,
          f"{k.target}{' (illustrative)' if k.target_is_illustrative else ''}" if k.target is not None else "--",
          k.status] for k in r.kpi_dashboard],
    ))

    out.append("## 4. Applicable Regulatory Requirements")
    out.append(_table(
        ["ID", "Regulation", "Authority", "Applicability", "Source", "Outdated?"],
        [[a["requirement_id"], a["regulation"], a["authority"], a["applicability_verdict"],
          f"[{a['source_title']}]({a['source_url']})", "YES" if a["potentially_outdated"] else "No"]
         for a in r.applicable_requirements],
    ))

    out.append("## 5. Compliance Status")
    out.append(_table(["Requirement", "Status"], [[rid, status] for rid, status in r.compliance_status.items()]))

    out.append("## 6. Key Gaps")
    out.append(_table(
        ["Priority", "Requirement", "Status", "Metric", "Actual", "Target", "Variance %"],
        [[g.priority_band or "--", g.requirement_id, g.status, g.metric or "--",
          f"{g.actual_value:.4f}" if g.actual_value is not None else "--",
          f"{g.target_value}{' (illustrative)' if g.target_is_illustrative else ''}" if g.target_value is not None else "--",
          f"{g.variance_pct:.1f}" if g.variance_pct is not None else "--"]
         for g in r.key_gaps],
    ))

    out.append("## 7. Root-Cause Analysis")
    if not r.root_cause_analysis:
        out.append("_No gap in this period met the threshold for an autonomous root-cause investigation._\n")
    for rc in r.root_cause_analysis:
        out.append(f"### {rc.requirement_id} -- {rc.metric} (trend: {rc.trend})")
        out.append("**Facts:**")
        out.extend(f"- {f}" for f in rc.facts)
        out.append("\n**Hypotheses (unconfirmed):**")
        out.extend(f"- ({h.confidence} confidence) {h.statement}" for h in rc.hypotheses)
        out.append("")

    out.append("## 8. Priority Actions")
    for i, action in enumerate(r.priority_actions, 1):
        out.append(f"### {i}. [{action['priority']}] {action['gap']}")
        out.append(f"- **Evidence:** {action['evidence']}")
        out.append(f"- **Root cause / suspected cause:** {action['root_cause']}")
        out.append(f"- **Corrective action:** {action['corrective_action']}")
        out.append(f"- **Suggested owner:** {action['suggested_owner']}")
        out.append(f"- **Suggested timeline:** {action['suggested_timeline']}")
        out.append(f"- **ESG impact:** {action['esg_impact']}")
        bi = action["business_impact"]
        out.append(f"- **Business impact:** {bi['summary']}")
        for k, v in bi["estimates"].items():
            out.append(f"    - *{k}*: {v}")
        out.append(f"- **Closure evidence:** {action['closure_evidence']}\n")
    if not r.priority_actions:
        out.append("_No corrective actions required for this period._\n")

    out.append("## 9. Evidence Status")
    out.append(_table(
        ["Requirement", "Regulation", "Evidence Status", "Missing", "Outdated"],
        [[e.requirement_id, e.regulation, e.evidence_status or "--",
          ", ".join(e.missing_evidence) or "--", ", ".join(e.outdated_evidence) or "--"]
         for e in r.evidence_status],
    ))

    out.append("## 10. Data Quality Issues")
    dq = r.data_quality_issues
    out.append(f"**Overall: {dq.overall}**\n")
    out.append(f"- Missing domains: {', '.join(dq.missing_domains) or 'None'}")
    out.append(f"- Conflicting domains: {', '.join(dq.conflicting_domains) or 'None'}")
    out.append(f"- Duplicate documents: {', '.join(dq.duplicate_documents) or 'None'}")
    if dq.flagged_issues:
        out.append("- Flagged issues:")
        for domain, issues in dq.flagged_issues.items():
            for issue in issues:
                out.append(f"    - **{domain}**: {issue}")
    out.append("")

    out.append("## 11. Assumptions")
    out.extend(f"- {a}" for a in r.assumptions)
    out.append("")

    out.append("## 12. Sources")
    out.append(_table(
        ["ID", "Title", "Authority", "Date", "Cited By"],
        [[s.source_id, f"[{s.title}]({s.url})", s.authority, s.date, ", ".join(s.cited_by)] for s in r.sources],
    ))

    out.append("## 13. Human Review Required")
    if not r.human_review_required:
        out.append("_None -- every applicable requirement was automatically classified._\n")
    for h in r.human_review_required:
        out.append(f"- **{h['requirement_id']}** ({h['regulation']}):")
        for reason in h["reasons"]:
            out.append(f"    - {reason}")

    return "\n".join(out) + "\n"


def render_pdf(report: ComplianceReport, path) -> None:
    """Best-effort PDF export via fpdf2's built-in core font (latin-1 only
    -- text is sanitized rather than risking a crash on a stray character).
    Markdown/JSON remain the primary, fully-detailed deliverables; this is
    a readable, single-column rendering of the same content for printing/
    sharing, not a pixel-perfect layout.

    `path` is whatever fpdf2's own `FPDF.output()` accepts: a filesystem
    path (str) or a writable file-like object (e.g. an `io.BytesIO` for
    serving the PDF over HTTP without touching disk -- see app.ui.server).
    """
    from fpdf import FPDF

    def clean(text: str) -> str:
        return str(text).encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def cell(text: str, height: float) -> None:
        # fpdf2 leaves the x cursor wherever the previous multi_cell ended
        # unless told otherwise -- reset to the left margin every time, or
        # a few calls in there is no horizontal room left to render at all.
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, height, clean(text))

    pdf.set_font("Helvetica", "B", 16)
    cell(f"ESG & Regulatory Compliance Report -- {report.plant}", 8)
    pdf.set_font("Helvetica", "", 10)
    cell(f"Reporting period: {report.period}    Generated: {report.generated_at}", 6)
    pdf.set_font("Helvetica", "I", 9)
    cell(report.disclaimer, 5)
    pdf.ln(2)

    def heading(text: str) -> None:
        pdf.set_font("Helvetica", "B", 13)
        pdf.ln(3)
        cell(text, 7)
        pdf.set_font("Helvetica", "", 10)

    def body(text: str) -> None:
        cell(text, 5.5)

    def bullet(text: str) -> None:
        cell(f"- {text}", 5.5)

    heading("1. Executive Summary")
    body(report.executive_summary)

    heading("2. Overall ESG Readiness Score")
    body(f"Overall: {report.readiness_score['overall_score']}/100")
    for c in report.readiness_score["breakdown"]:
        bullet(f"{c.category} (weight {c.weight:.0%}): {c.score:.1f}/100 -- {c.reason}")

    heading("3. KPI Dashboard")
    for k in report.kpi_dashboard:
        value = k.value if k.value is not None else "N/A"
        target = f", target {k.target}" if k.target is not None else ""
        bullet(f"{k.name}: {value} {k.unit}{target} ({k.status})")

    heading("4. Applicable Regulatory Requirements")
    for a in report.applicable_requirements:
        flag = " [POTENTIALLY OUTDATED]" if a["potentially_outdated"] else ""
        bullet(f"{a['requirement_id']} -- {a['regulation']} ({a['applicability_verdict']}){flag}")

    heading("5. Compliance Status")
    for rid, status in report.compliance_status.items():
        bullet(f"{rid}: {status}")

    heading("6. Key Gaps")
    for g in report.key_gaps:
        bullet(f"[{g.priority_band}] {g.requirement_id} -- {g.status} (metric={g.metric}, actual={g.actual_value}, target={g.target_value})")

    heading("7. Root-Cause Analysis")
    if not report.root_cause_analysis:
        body("No gap in this period met the threshold for an autonomous root-cause investigation.")
    for rc in report.root_cause_analysis:
        body(f"{rc.requirement_id} -- {rc.metric} (trend: {rc.trend})")
        for f in rc.facts:
            bullet(f"FACT: {f}")
        for h in rc.hypotheses:
            bullet(f"HYPOTHESIS ({h.confidence} confidence): {h.statement}")

    heading("8. Priority Actions")
    for i, action in enumerate(report.priority_actions, 1):
        body(f"{i}. [{action['priority']}] {action['gap']}")
        bullet(f"Corrective action: {action['corrective_action']}")
        bullet(f"Owner: {action['suggested_owner']}  Timeline: {action['suggested_timeline']}")
        bullet(f"Business impact: {action['business_impact']['summary']}")

    heading("9. Evidence Status")
    for e in report.evidence_status:
        bullet(f"{e.requirement_id}: {e.evidence_status} (missing: {', '.join(e.missing_evidence) or 'none'})")

    heading("10. Data Quality Issues")
    dq = report.data_quality_issues
    body(f"Overall: {dq.overall}")
    bullet(f"Missing: {', '.join(dq.missing_domains) or 'None'}")
    bullet(f"Conflicting: {', '.join(dq.conflicting_domains) or 'None'}")
    bullet(f"Duplicate documents: {', '.join(dq.duplicate_documents) or 'None'}")

    heading("11. Assumptions")
    for a in report.assumptions:
        bullet(a)

    heading("12. Sources")
    for s in report.sources:
        bullet(f"[{s.source_id}] {s.title} ({s.authority}, {s.date}) -- cited by {', '.join(s.cited_by)}")

    heading("13. Human Review Required")
    if not report.human_review_required:
        body("None -- every applicable requirement was automatically classified.")
    for h in report.human_review_required:
        bullet(f"{h['requirement_id']} ({h['regulation']})")

    pdf.output(path)
