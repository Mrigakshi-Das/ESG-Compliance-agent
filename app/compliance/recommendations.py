"""Builds a corrective-action recommendation from a prioritized Gap.

Every recommendation carries exactly the fields the project brief asks
for: gap, evidence, root cause / suspected cause, corrective action,
suggested owner, suggested timeline, ESG impact, business impact, and
closure evidence. Root cause is always phrased as a Hypothesis (never a
confirmed Fact) unless no investigation was run at all, in which case that
is said plainly instead of inventing one.
"""

from typing import Any

from app.compliance.types import Gap

_OWNER_BY_STATUS: dict[str, str] = {
    "Potential Gap": "Plant Energy/Environment Manager",
    "Evidence Missing": "Compliance / Company Secretary function",
    "Evidence Outdated": "Compliance / Company Secretary function",
    "Data Missing": "Plant Data/MIS team",
    "Data Conflict": "Plant Data/MIS team, in coordination with the ESG reporting system owner",
    "Human Review Required": "Corporate Compliance (confirm regulatory applicability)",
}

_TIMELINE_BY_URGENCY: dict[int, str] = {
    5: "Immediate (within 2 weeks)",
    4: "Within 30 days",
    3: "Before the next reporting cycle",
    2: "Next reporting cycle",
    1: "Next annual review",
}

_ESG_IMPACT_BY_STATUS: dict[str, str] = {
    "Potential Gap": "Leaving this unaddressed risks continued elevated emission/energy intensity and weaker "
                     "ESG performance disclosure for this plant.",
    "Evidence Missing": "Without this evidence, ESG/regulatory claims for this requirement cannot be substantiated "
                        "in an audit or assurance review, regardless of actual operational performance.",
    "Evidence Outdated": "An expired document is functionally the same as missing evidence to an auditor -- "
                         "the underlying compliance may be fine, but it cannot currently be demonstrated.",
    "Data Missing": "A gap in the reporting record weakens the completeness of this plant's ESG disclosures.",
    "Data Conflict": "Reporting a disputed figure risks a restatement or credibility question if the "
                     "discrepancy surfaces during external assurance.",
    "Human Review Required": "Regulatory scope for this requirement is unresolved; the plant may be over- or "
                             "under-reporting relative to its actual obligations.",
}


def _corrective_action(gap: Gap) -> str:
    if gap.status == "Potential Gap" and gap.metric:
        return (
            f"Investigate and address the operational driver(s) behind the {gap.metric} gap "
            "(see root cause) and re-verify after the next full reporting cycle."
        )
    if gap.status == "Evidence Missing":
        items = ", ".join(gap.missing_evidence) or "the required document(s)"
        return f"Obtain and file the missing evidence: {items}."
    if gap.status == "Evidence Outdated":
        return "Renew the outdated evidence and file the updated document before the next reporting cycle."
    if gap.status == "Data Conflict":
        return "Reconcile the conflicting source records with the systems of record before relying on this figure for reporting."
    if gap.status == "Data Missing":
        return "Investigate why the required data was not recorded/submitted for this period, and backfill or document the gap."
    if gap.status == "Human Review Required":
        return (
            "Confirm applicability against the authoritative external record (e.g. the BEE gazette "
            "Designated Consumer / obligated-entity list, or the company's SEBI market-capitalization rank) "
            "before treating this requirement as in-scope or out-of-scope."
        )
    return "Review this item with the relevant function owner."


def _evidence_summary(gap: Gap) -> str:
    parts = []
    if gap.missing_evidence:
        parts.append(f"missing: {', '.join(gap.missing_evidence)}")
    if gap.outdated_evidence:
        parts.append(f"outdated: {', '.join(gap.outdated_evidence)}")
    if gap.conflicting_evidence:
        parts.append(f"conflicting: {len(gap.conflicting_evidence)} item(s)")
    if gap.actual_value is not None:
        parts.append(f"calculated value: {gap.actual_value:.4f}" + (f" vs. target {gap.target_value}" if gap.target_value is not None else ""))
    return "; ".join(parts) if parts else "No specific evidence item identified for this gap."


def _root_cause_summary(gap: Gap) -> str:
    if gap.root_cause is None:
        return "Not investigated (no significant performance gap triggered a root-cause investigation)."
    hypotheses = [f.statement for f in gap.root_cause.findings if f.kind == "Hypothesis"]
    if not hypotheses:
        return "Investigated; no specific contributing factor could be identified from available data."
    return "Hypothesis: " + " | ".join(hypotheses)


def _closure_evidence(gap: Gap) -> str:
    if gap.status == "Potential Gap":
        return f"A subsequent period's {gap.metric} calculation showing the value back within target, retained with its source data."
    if gap.status in ("Evidence Missing", "Evidence Outdated"):
        return "The filed replacement/renewed document, indexed against this requirement's required_evidence."
    if gap.status == "Data Conflict":
        return "A reconciliation record showing the corrected, single agreed value and which source system it came from."
    if gap.status == "Data Missing":
        return "The backfilled data record, or a documented explanation for why it is permanently unavailable."
    if gap.status == "Human Review Required":
        return "A written applicability determination (e.g. confirmed DC/obligated-entity status or market-cap rank) from the responsible function."
    return "N/A"


def _business_impact(gap: Gap) -> dict[str, Any]:
    summary = {
        "Potential Gap": "Sustained improvement would reduce regulatory and reputational exposure and may lower operating cost.",
        "Evidence Missing": "Avoids audit findings/qualifications in the next assurance cycle.",
        "Evidence Outdated": "Avoids audit findings/qualifications in the next assurance cycle.",
        "Data Conflict": "Avoids a reporting restatement risk.",
        "Data Missing": "Improves completeness of the reporting record for the next assurance cycle.",
        "Human Review Required": "Clarifies actual regulatory exposure/obligation for this plant.",
    }.get(gap.status, "Not characterized.")

    if gap.estimated_impact:
        return {"summary": summary, "estimates": gap.estimated_impact}
    return {
        "summary": summary,
        "estimates": {"note": "No quantified estimate available for this gap (insufficient data to ground one)."},
    }


def build_recommendation(gap: Gap) -> dict[str, Any]:
    urgency_key = round(gap.urgency) if gap.urgency is not None else 3
    return {
        "gap": f"{gap.requirement_id} ({gap.regulation}): {gap.status}",
        "evidence": _evidence_summary(gap),
        "root_cause": _root_cause_summary(gap),
        "corrective_action": _corrective_action(gap),
        "suggested_owner": _OWNER_BY_STATUS.get(gap.status, "Plant Management"),
        "suggested_timeline": _TIMELINE_BY_URGENCY.get(urgency_key, "Next reporting cycle"),
        "esg_impact": _ESG_IMPACT_BY_STATUS.get(gap.status, "Not characterized."),
        "business_impact": _business_impact(gap),
        "closure_evidence": _closure_evidence(gap),
        "priority": gap.priority_band,
        "priority_score": gap.priority_score,
    }
