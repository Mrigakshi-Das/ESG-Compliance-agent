"""Top-level compliance assessment: composes every Phase 6 engine into one
call, `run_compliance_assessment(plant, period)`.

Pipeline: applicable requirements (Phase 4) -> per-requirement numeric +
evidence evaluation -> status classification (gap_analysis) -> root-cause
investigation for eligible numeric gaps (gap_analysis) -> business-impact
estimation (this module) -> prioritization -> corrective-action
recommendations. Each stage is independently testable; this module's own
job is only the wiring and the two engine-level policy calls documented
inline (the "no target at all" override, and which metrics are eligible
for a quantified business-impact estimate).
"""

from dataclasses import dataclass, field
from typing import Any

from app.calculations.scoring import calculate_overall_readiness_score, compare_with_target
from app.compliance.context import ASSUMPTION_NOTES
from app.compliance.data_quality import DataQualityReport, assess_data_quality
from app.compliance.gap_analysis import classify_requirement_status, investigate_root_cause
from app.compliance.prioritization import prioritize_gaps
from app.compliance.recommendations import build_recommendation
from app.compliance.requirements import get_applicable_requirements
from app.compliance.types import Gap
from app.data.regulatory_targets import load_regulatory_targets
from app.tools.analytics import get_historical_metric
from app.tools.documents import search_documents
from app.tools.emissions import get_emission_data
from app.tools.energy import get_energy_data
from app.tools.evidence import assess_evidence
from app.tools.metrics import fetch_metric_value
from app.tools.production import get_production_data

# requirement_id -> (METRIC_REGISTRY key, illustrative-target metric label
# in app.data.regulatory_targets). Only requirements with a metric our tool
# layer can actually compute get an entry; the rest are evidence/
# applicability-only by nature (see their `unit: "N/A"` in the KB).
_REQUIREMENT_METRIC_MAP: dict[str, tuple[str, str]] = {
    "BEE-PAT-002": ("specific_thermal_energy_consumption_gj_per_t_clinker", "Specific Thermal Energy Consumption"),
    "BEE-CCTS-002": ("emission_intensity_tco2e_per_t_cement", "GHG Emission Intensity"),
}

# Root-cause investigation and business-impact estimation only make sense
# for metrics with a real driver chain behind them.
_ROOT_CAUSE_ELIGIBLE_METRICS = {
    "emission_intensity_tco2e_per_t_cement",
    "energy_intensity_kwh_per_t_cement",
    "specific_thermal_energy_consumption_gj_per_t_clinker",
}

# Each Phase 4 requirement's `required_evidence` is deliberately a
# human-readable citation (e.g. "GHG Verification Statement / accredited
# carbon verification agency report") for the knowledge base's own sake --
# it is shown as-is in recommendations. `assess_evidence` matching, though,
# is a substring check against the plant's actual short document_type
# values (see app/data/DATA_DICTIONARY.md), so it needs its own short,
# matchable labels here instead. An empty list means no evidence type in
# our synthetic vocabulary corresponds to this requirement -- evidence is
# simply not assessed for it (harmless for PAT/CCTS, whose applicability is
# Human Review Required regardless of evidence). Public (not `_`-prefixed):
# `app.agent.orchestrator`'s evidence_audit intent reuses this directly --
# it used to build its own required-types list straight from the KB's
# descriptive text, which could never substring-match anything and made
# every evidence audit report "Missing" regardless of what was on file.
REQUIREMENT_EVIDENCE_TYPES: dict[str, list[str]] = {
    "BEE-CCTS-002": ["GHG Verification Statement"],
    "SEBI-BRSR-001": ["BRSR Annual Report"],
    "SEBI-BRSRCORE-001": ["BRSR Core KPI Disclosure"],
    "SEBI-BRSRCORE-002": ["GHG Verification Statement", "BRSR Core Assurance Statement"],
    "SEBI-BRSRCORE-003": ["Value Chain ESG Disclosure"],
}


@dataclass
class ComplianceAssessment:
    plant: str
    period: str
    data_quality: DataQualityReport
    requirement_statuses: dict[str, str] = field(default_factory=dict)
    gaps: list[Gap] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    overall_readiness_score: int = 0
    assumptions: list[str] = field(default_factory=list)


def find_illustrative_target(plant: str, metric_label: str) -> float | None:
    for row in load_regulatory_targets():
        applies = plant in row["applicability"] or "All plants" in row["applicability"]
        if applies and metric_label.lower() in row["metric"].lower():
            try:
                return float(row["target"])
            except (TypeError, ValueError):
                continue
    return None


def _estimate_business_impact(plant: str, period: str, gap: Gap) -> dict[str, Any] | None:
    if gap.metric in ("emission_intensity_tco2e_per_t_cement", "specific_thermal_energy_consumption_gj_per_t_clinker"):
        driver_metric = "specific_thermal_energy_consumption_gj_per_t_clinker"
    elif gap.metric == "energy_intensity_kwh_per_t_cement":
        driver_metric = "specific_electricity_consumption_kwh_per_t_cement"
    else:
        return None

    history = get_historical_metric(plant, driver_metric)
    ok_values = [s["value"] for s in history["series"] if s["status"] == "ok"]
    if len(ok_values) < 2:
        return None
    best, current = min(ok_values), ok_values[-1]
    if current <= best:
        return None
    reduction_fraction = (current - best) / current

    production = get_production_data(plant, period)
    energy = get_energy_data(plant, period)
    emissions = get_emission_data(plant, period)
    if production["status"] != "ok" or energy["status"] != "ok" or emissions["status"] != "ok":
        return None

    estimate: dict[str, Any] = {
        "basis": (
            f"Estimate: if {driver_metric} were restored to this plant's own best observed value in the "
            f"configured history ({best:.3f} vs. the current {current:.3f}), scaled against the current "
            "period's actual energy/emissions. Illustrative, based on this plant's own historical "
            "variation -- not a guaranteed outcome -- and assumes Scope 1/2 emissions scale "
            "proportionally with the driver metric."
        ),
    }
    if driver_metric == "specific_thermal_energy_consumption_gj_per_t_clinker":
        estimate["potential_energy_savings_gj_estimate"] = round(reduction_fraction * energy["values"]["thermal_energy_gj"], 1)
        estimate["potential_emission_reduction_tco2e_estimate"] = round(reduction_fraction * emissions["values"]["scope_1_tco2e"], 1)
    else:
        estimate["potential_energy_savings_mwh_estimate"] = round(reduction_fraction * energy["values"]["electricity_consumption_mwh"], 1)
        estimate["potential_emission_reduction_tco2e_estimate"] = round(reduction_fraction * emissions["values"]["scope_2_tco2e"], 1)
    estimate["potential_cost_impact"] = "Not estimated -- no energy/fuel cost data is configured in this system."
    return estimate


# Operational performance is checked independently of regulatory
# applicability: whether CCTS/PAT formally attaches to this exact plant is
# genuinely uncertain (see BEE-CCTS-002/BEE-PAT-002, both Human Review
# Required for that reason) -- but "is this plant's emission/energy
# intensity worse than its own reasonable benchmark" is a legitimate ESG
# management question regardless of which specific law turns out to apply,
# and root-cause investigation should not be gated on resolving that legal
# question first.
_OPERATIONAL_BENCHMARKS: dict[str, str] = {
    "emission_intensity_tco2e_per_t_cement": "GHG Emission Intensity",
    "specific_thermal_energy_consumption_gj_per_t_clinker": "Specific Thermal Energy Consumption",
}


def _operational_performance_gaps(plant: str, period: str) -> list[Gap]:
    gaps: list[Gap] = []
    for metric_key, target_label in _OPERATIONAL_BENCHMARKS.items():
        mv = fetch_metric_value(plant, period, metric_key)
        if mv.status != "ok":
            continue
        target = find_illustrative_target(plant, target_label)
        if target is None:
            continue
        comparison = compare_with_target(mv.value, target, metric_key)
        if comparison["status"] == "Within Target":
            continue

        gap = Gap(
            plant=plant, period=period,
            requirement_id=f"INTERNAL-{metric_key.upper()}",
            regulation="Internal ESG performance benchmark (illustrative -- not a regulatory determination)",
            status="Potential Gap", metric=metric_key, actual_value=mv.value,
            target_value=target, target_is_illustrative=True,
            variance_pct=comparison["percentage_variance"],
            notes=[
                f"Benchmarked against an illustrative internal target ({target}), not a confirmed regulatory "
                "obligation -- the corresponding regulatory item is Human Review Required pending applicability "
                "confirmation (see BEE-CCTS-002 / BEE-PAT-002)."
            ],
        )
        if metric_key in _ROOT_CAUSE_ELIGIBLE_METRICS:
            gap.root_cause = investigate_root_cause(plant, metric_key)
            gap.estimated_impact = _estimate_business_impact(plant, period, gap)
        gaps.append(gap)
    return gaps


def run_compliance_assessment(plant: str, period: str) -> ComplianceAssessment:
    data_quality = assess_data_quality(plant, period)
    # get_applicable_requirements takes no period: BRSR/BRSR Core/GHG
    # verification are annual, company-level filings made months after the
    # fiscal year they report on, so they never "cover" a single quarter the
    # way a time-bound calibration certificate does (see
    # app.data.evidence._covers_period, which is designed for the latter).
    # Currency is instead checked by assess_evidence's own expiry/as_of_date
    # logic below.
    applicable = get_applicable_requirements(plant)
    documents = search_documents(plant)

    gaps: list[Gap] = []
    statuses: dict[str, str] = {}

    for item in applicable:
        req = item.requirement
        metric_status = None
        target_comparison = None
        actual_value = None
        target_value = None
        target_is_illustrative = False

        mapped = _REQUIREMENT_METRIC_MAP.get(req.requirement_id)
        if mapped and item.applicability_verdict == "Applicable":
            metric_key, target_label = mapped
            mv = fetch_metric_value(plant, period, metric_key)
            metric_status = mv.status
            if mv.status == "ok":
                actual_value = mv.value
                target_value = find_illustrative_target(plant, target_label)
                if target_value is not None:
                    target_is_illustrative = True
                    target_comparison = compare_with_target(mv.value, target_value, metric_key)

        evidence_status = None
        evidence_result = None
        evidence_types = REQUIREMENT_EVIDENCE_TYPES.get(req.requirement_id, [])
        if evidence_types:
            evidence_result = assess_evidence(
                {"required_document_types": evidence_types},
                documents.get("documents", []),
            )
            evidence_status = evidence_result["evidence_status"]

        status = classify_requirement_status(item.applicability_verdict, metric_status, target_comparison, evidence_status)

        # Engine-level policy: a requirement with a computable value but no
        # target at all (sourced or illustrative) to compare it against
        # cannot honestly be reported Compliant -- that's a human call, not
        # an automatic pass.
        no_target_note = None
        if mapped and metric_status == "ok" and target_comparison is None and status == "Compliant":
            status = "Human Review Required"
            no_target_note = f"No numeric target (sourced or illustrative) is configured to compare {mapped[0]} against for {plant}."

        statuses[req.requirement_id] = status

        if status in ("Compliant", "Not Applicable"):
            continue

        notes = list(item.applicability_reasons) if item.applicability_verdict != "Applicable" else []
        if no_target_note:
            notes.append(no_target_note)

        evaluated_metric = mapped[0] if (mapped and item.applicability_verdict == "Applicable") else None
        gap = Gap(
            plant=plant, period=period, requirement_id=req.requirement_id, regulation=req.regulation,
            status=status, metric=evaluated_metric, actual_value=actual_value,
            target_value=target_value, target_is_illustrative=target_is_illustrative,
            variance_pct=target_comparison["percentage_variance"] if target_comparison else None,
            evidence_status=evidence_status,
            missing_evidence=evidence_result["missing_evidence"] if evidence_result else [],
            outdated_evidence=[d["document_id"] for d in evidence_result["outdated_evidence"]] if evidence_result else [],
            conflicting_evidence=evidence_result["conflicting_evidence"] if evidence_result else [],
            notes=notes,
        )

        if gap.metric in _ROOT_CAUSE_ELIGIBLE_METRICS and status == "Potential Gap":
            gap.root_cause = investigate_root_cause(plant, gap.metric)
            gap.estimated_impact = _estimate_business_impact(plant, period, gap)

        gaps.append(gap)

    gaps.extend(_operational_performance_gaps(plant, period))
    gaps = prioritize_gaps(gaps)
    recommendations = [build_recommendation(g) for g in gaps]
    overall_score = calculate_overall_readiness_score(statuses)

    return ComplianceAssessment(
        plant=plant, period=period, data_quality=data_quality, requirement_statuses=statuses,
        gaps=gaps, recommendations=recommendations, overall_readiness_score=overall_score,
        assumptions=list(ASSUMPTION_NOTES),
    )
