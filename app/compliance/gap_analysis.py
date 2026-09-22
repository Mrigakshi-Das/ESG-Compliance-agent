"""Per-requirement compliance classification and root-cause investigation.

Two independent responsibilities:

- `classify_requirement_status` combines a numeric target comparison (if
  the requirement has a computable metric) with an evidence assessment
  into one of the 8 statuses the project brief defines, using a fixed
  severity order rather than nested special cases.
- `investigate_root_cause` walks the production -> electricity -> thermal
  energy -> fuel -> maintenance chain the brief describes, then extends
  that with a broader, still-deterministic scan across fuel-quality and
  weather data (`_EXTERNAL_FACTOR_CHAIN`), and finally an *optional*
  LLM-assisted exploration for genuinely novel hypotheses beyond either
  hand-coded chain when `ANTHROPIC_API_KEY` is configured. All three stages
  are careful to never present an inferred connection as a proven one:
  every statement produced is tagged Fact (a real change the data shows)
  or Hypothesis (a plausible, unconfirmed explanation for it), and the
  LLM stage is additionally constrained to reason only over Facts already
  established by the deterministic stages -- it is never asked to invent
  a number or a data point.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from app.calculations.scoring import ComplianceStatus
from app.tools.analytics import get_historical_metric
from app.tools.maintenance import get_maintenance_data

# ---------------------------------------------------------------------------
# Compliance status classification
# ---------------------------------------------------------------------------

# Severity order used when both a numeric target problem and an evidence
# problem are present at once -- the more fundamental problem (can we even
# see the evidence?) is reported over the more specific one (is the number
# within target?), since a number can't be trusted without evidence anyway.
_SEVERITY_ORDER: tuple[ComplianceStatus, ...] = (
    "Data Conflict", "Evidence Outdated", "Evidence Missing", "Potential Gap",
)

_EVIDENCE_STATUS_TO_COMPLIANCE: dict[str, ComplianceStatus] = {
    "Conflicting": "Data Conflict",
    "Outdated": "Evidence Outdated",
    "Missing": "Evidence Missing",
    "Mixed": "Potential Gap",
}


def classify_requirement_status(
    applicability_verdict: Literal["Applicable", "Not Applicable", "Cannot Determine"],
    metric_status: Literal["ok", "missing", "conflict"] | None,
    target_comparison: dict[str, Any] | None,
    evidence_status: str | None,
) -> ComplianceStatus:
    """
    applicability_verdict: from app.regulations.applicability.
    metric_status: the get_*_data status backing the requirement's metric,
        or None if the requirement has no computable numeric metric.
    target_comparison: compare_with_target's result if a target exists, else None.
    evidence_status: assess_evidence's evidence_status, or None if the
        requirement's required_evidence could not be assessed at all.
    """
    if applicability_verdict == "Not Applicable":
        return "Not Applicable"
    if applicability_verdict == "Cannot Determine":
        return "Human Review Required"

    if metric_status == "conflict":
        return "Data Conflict"
    if metric_status == "missing":
        return "Data Missing"

    candidates: list[ComplianceStatus] = []
    if evidence_status in _EVIDENCE_STATUS_TO_COMPLIANCE:
        candidates.append(_EVIDENCE_STATUS_TO_COMPLIANCE[evidence_status])
    if target_comparison is not None and target_comparison.get("status") != "Within Target":
        candidates.append("Potential Gap")

    if not candidates:
        return "Compliant"
    for status in _SEVERITY_ORDER:
        if status in candidates:
            return status
    return "Compliant"  # unreachable given the map above, kept for exhaustiveness


# ---------------------------------------------------------------------------
# Root-cause investigation
# ---------------------------------------------------------------------------

_TREND_TOLERANCE_PCT = 2.0  # matches app.tools.analytics's own trend tolerance

# Which historical driver metrics to check, and which maintenance-equipment
# keywords would plausibly explain a rise in that driver. Order matters: it
# is the causal chain order the brief specifies (production -> electricity
# -> thermal energy -> fuel), read here innermost-to-outermost from the
# emissions/energy metric being investigated.
_DRIVER_CHAIN: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("specific_thermal_energy_consumption_gj_per_t_clinker", ("kiln", "refractory", "burner")),
    ("specific_electricity_consumption_kwh_per_t_cement", ("mill", "motor", "bearing", "fan")),
    ("fuel_consumption_tonnes", ("fuel", "coal", "kiln")),
    ("alternative_fuel_thermal_substitution_pct", ("afr", "alternative fuel", "kiln")),
)
_PRODUCTION_METRIC = "clinker_production_tonnes"


@dataclass(frozen=True)
class ExternalFactor:
    metric: str
    concerning_direction: Literal["increase", "decrease"]
    hypothesis: str


# Broader, still-deterministic scan beyond the original chain above: fuel
# quality and ambient weather signals that plausibly affect kiln thermal
# efficiency specifically (combustion quality, raw-material drying load).
# Checked only when specific_thermal_energy_consumption_... is itself a
# notable driver in this investigation, so a hypothesis never gets attached
# to a metric it has no plausible causal link to (e.g. ash content has
# nothing to do with an electricity-only investigation).
#
# Each factor has exactly one "concerning" direction, and is only surfaced
# when the data actually moved that way -- weather in particular swings
# with season regardless of any real trend, so a factor that moved in the
# *helpful* direction (e.g. rainfall fell) is not reported as if it
# explained a rise; it simply isn't relevant to this investigation. This is
# the same discipline the original _DRIVER_CHAIN gets for free from every
# one of its metrics already having an unambiguous "bad" direction.
_EXTERNAL_FACTOR_CHAIN: tuple[ExternalFactor, ...] = (
    ExternalFactor(
        "gross_calorific_value_kcal_per_kg", "decrease",
        "a lower fuel gross calorific value may require burning more fuel mass to sustain the same kiln heat duty, which can raise specific thermal energy consumption",
    ),
    ExternalFactor(
        "ash_content_pct", "increase",
        "a rise in fuel ash content can reduce effective combustion efficiency, which may raise specific thermal energy consumption",
    ),
    ExternalFactor(
        "moisture_content_pct", "increase",
        "a rise in fuel moisture content consumes additional energy for evaporation before combustion, which may raise specific thermal energy consumption",
    ),
    ExternalFactor(
        "rainfall_mm", "increase",
        "higher rainfall can raise raw-material moisture, which may increase the thermal energy needed for pre-drying",
    ),
    ExternalFactor(
        "avg_humidity_pct", "increase",
        "higher ambient humidity can raise raw-material moisture, which may increase the thermal energy needed for pre-drying",
    ),
)

_THERMAL_METRIC = "specific_thermal_energy_consumption_gj_per_t_clinker"


@dataclass
class RootCauseFinding:
    kind: Literal["Fact", "Hypothesis"]
    statement: str
    confidence: Literal["High", "Medium", "Low"]


@dataclass
class RootCauseInvestigation:
    plant: str
    metric: str
    trend: str
    findings: list[RootCauseFinding] = field(default_factory=list)
    contributing_factors: list[str] = field(default_factory=list)


def _series_pct_change(series: list[dict[str, Any]]) -> float | None:
    ok_values = [s["value"] for s in series if s["status"] == "ok"]
    if len(ok_values) < 2 or ok_values[0] == 0:
        return None
    return (ok_values[-1] - ok_values[0]) / abs(ok_values[0]) * 100


def investigate_root_cause(
    plant: str, metric: str, llm_client_override: Any | None = None,
) -> RootCauseInvestigation:
    """`llm_client_override` is injectable for testing the optional LLM
    exploration stage against a scripted fake client, exactly like
    `app.agent.llm_client.run_agentic_loop`'s `client` parameter -- it is
    not meant to be passed by ordinary callers."""
    history = get_historical_metric(plant, metric)
    investigation = RootCauseInvestigation(plant=plant, metric=metric, trend=history["trend"])

    if history["trend"] in ("flat", "decreasing", "insufficient_data"):
        investigation.findings.append(RootCauseFinding(
            "Fact",
            f"{plant}'s {metric} does not show a sustained increase across the configured periods "
            f"(trend: {history['trend']}); no root-cause investigation is warranted.",
            "High",
        ))
        return investigation

    target_pct = _series_pct_change(history["series"])
    investigation.findings.append(RootCauseFinding(
        "Fact",
        f"{plant}'s {metric} increased {target_pct:.1f}% across the configured periods." if target_pct is not None
        else f"{plant}'s {metric} trend is increasing.",
        "High",
    ))

    notable_drivers: list[tuple[str, float]] = []
    for driver_metric, _keywords in _DRIVER_CHAIN:
        driver_history = get_historical_metric(plant, driver_metric)
        pct = _series_pct_change(driver_history["series"])
        if pct is None:
            continue
        if abs(pct) > _TREND_TOLERANCE_PCT:
            direction = "increased" if pct > 0 else "decreased"
            investigation.findings.append(RootCauseFinding(
                "Fact",
                f"{plant}'s {driver_metric} {direction} {abs(pct):.1f}% across the configured periods.",
                "High",
            ))
            notable_drivers.append((driver_metric, pct))

    production_history = get_historical_metric(plant, _PRODUCTION_METRIC)
    production_pct = _series_pct_change(production_history["series"])
    if production_pct is not None and production_pct < -_TREND_TOLERANCE_PCT:
        investigation.findings.append(RootCauseFinding(
            "Fact", f"{plant}'s {_PRODUCTION_METRIC} decreased {abs(production_pct):.1f}% across the configured periods.", "High",
        ))
        investigation.findings.append(RootCauseFinding(
            "Hypothesis",
            f"Part of the rise in {metric} may reflect lower production volume over the period "
            "(fixed and semi-fixed emissions/energy spread over less output) rather than a change "
            "in process efficiency.",
            "Medium",
        ))
        investigation.contributing_factors.append(f"Declining {_PRODUCTION_METRIC.replace('_', ' ')}")

    maintenance = get_maintenance_data(plant)
    overdue = [r for r in maintenance["records"] if r["maintenance_status"] == "Overdue"]
    matched_equipment: set[str] = set()
    for driver_metric, keywords in _DRIVER_CHAIN:
        if not any(dm == driver_metric for dm, _ in notable_drivers):
            continue
        for record in overdue:
            haystack = f"{record['equipment']} {record['issue']}".lower()
            if record["equipment"] in matched_equipment:
                continue
            if any(k in haystack for k in keywords):
                matched_equipment.add(record["equipment"])
                investigation.findings.append(RootCauseFinding(
                    "Hypothesis",
                    f"The increase in {driver_metric} may be related to an unaddressed maintenance issue: "
                    f"'{record['equipment']}' has been Overdue since {record['planned_next_maintenance']} "
                    f"({record['issue']}).",
                    "Medium",
                ))
                investigation.contributing_factors.append(f"Overdue maintenance: {record['equipment']}")

    # Broader deterministic scan: fuel-quality and weather signals, checked
    # only when thermal energy is itself a notable driver (see
    # _EXTERNAL_FACTOR_CHAIN's docstring for why). Works with no API key --
    # this is the "no-key fallback" for hypotheses outside the original
    # production/electricity/thermal/fuel/maintenance chain.
    if any(dm == _THERMAL_METRIC for dm, _ in notable_drivers):
        for factor in _EXTERNAL_FACTOR_CHAIN:
            factor_history = get_historical_metric(plant, factor.metric)
            pct = _series_pct_change(factor_history["series"])
            if pct is None or abs(pct) <= _TREND_TOLERANCE_PCT:
                continue
            direction = "increased" if pct > 0 else "decreased"
            moved_concerning_way = (direction == "increased") == (factor.concerning_direction == "increase")
            if not moved_concerning_way:
                continue  # moved the helpful way (e.g. rainfall fell) -- not relevant to this rise
            investigation.findings.append(RootCauseFinding(
                "Fact",
                f"{plant}'s {factor.metric} {direction} {abs(pct):.1f}% across the configured periods.",
                "High",
            ))
            investigation.findings.append(RootCauseFinding(
                "Hypothesis", f"{factor.hypothesis[0].upper()}{factor.hypothesis[1:]}.", "Medium",
            ))
            investigation.contributing_factors.append(f"External factor: {factor.metric} {direction} {abs(pct):.1f}%")

    # Optional, genuinely open-ended stage: only runs with ANTHROPIC_API_KEY
    # configured (see app.agent.llm_client.is_available). Everything above
    # this point is deterministic and identical whether or not a key is set.
    llm_findings = _llm_explore_additional_hypotheses(plant, metric, investigation, llm_client_override)
    if llm_findings:
        investigation.findings.extend(llm_findings)
        investigation.contributing_factors.append("LLM-identified additional hypothesis")

    if not investigation.contributing_factors:
        investigation.findings.append(RootCauseFinding(
            "Hypothesis",
            f"{plant}'s {metric} is rising, but no overdue maintenance record or production decline was found "
            "to corroborate a specific cause; further investigation (e.g. fuel-mix or process review) is recommended.",
            "Low",
        ))

    return investigation


def _llm_explore_additional_hypotheses(
    plant: str,
    metric: str,
    investigation: RootCauseInvestigation,
    client_override: Any | None = None,
) -> list[RootCauseFinding]:
    """Optional extension to the two deterministic scans above. When
    `ANTHROPIC_API_KEY` is configured (see `app.agent.llm_client.
    is_available`), asks a real Claude client to suggest additional
    plausible causal hypotheses -- genuinely open-ended, not limited to the
    hand-coded `_DRIVER_CHAIN` / `_EXTERNAL_FACTOR_CHAIN` above -- but
    constrained to reason only over the Facts this investigation has
    already established; it is never asked to invent a number or a fact.
    Without a key (or on any network/parsing failure), this is a no-op and
    the deterministic scans above remain the whole result -- an LLM outage
    must never break or change the grounded part of the investigation.

    `client_override` is injectable for testing against a scripted fake
    client, exactly like `app.agent.llm_client.run_agentic_loop`'s `client`.
    """
    from app.agent import llm_client

    client = client_override
    if client is None:
        if not llm_client.is_available():
            return []
        client = llm_client.get_client()

    known_facts = [f.statement for f in investigation.findings if f.kind == "Fact"]
    known_hypotheses = [f.statement for f in investigation.findings if f.kind == "Hypothesis"]
    if not known_facts:
        return []

    system = (
        "You are assisting a root-cause investigation for a cement plant ESG "
        "compliance agent. You will be given a JSON bundle of ALREADY-VERIFIED "
        "facts about one plant/metric's trend, plus hypotheses a deterministic "
        "scan has already identified. Suggest 0 to 3 ADDITIONAL plausible "
        "causal hypotheses that are genuinely different from the ones already "
        "listed. Use ONLY the facts given below -- never invent a number, a "
        "data point, or a fact not present in this bundle. Each hypothesis "
        "must be phrased as a possibility ('may be related to', 'could "
        "contribute to'), never asserted as certain. Respond with ONLY a JSON "
        'array, e.g. [{"statement": "...", "confidence": "Medium"}]. '
        'Confidence must be "Medium" or "Low" -- never "High", since a '
        "hypothesis is by definition unconfirmed. Return [] if you have "
        "nothing genuinely new to add."
    )
    payload = json.dumps({
        "plant": plant,
        "metric": metric,
        "trend": investigation.trend,
        "known_facts": known_facts,
        "already_identified_hypotheses": known_hypotheses,
    })

    try:
        response = client.create_message(
            model=llm_client.MODEL,
            max_tokens=512,
            system=system,
            messages=[{"role": "user", "content": payload}],
        )
        text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text").strip()
        parsed = json.loads(text)
    except Exception:
        return []  # a network/parsing failure must never break the deterministic result

    findings: list[RootCauseFinding] = []
    if isinstance(parsed, list):
        for item in parsed:
            if not isinstance(item, dict):
                continue
            statement = item.get("statement")
            confidence = item.get("confidence")
            if isinstance(statement, str) and statement and confidence in ("Medium", "Low"):
                findings.append(RootCauseFinding("Hypothesis", statement, confidence))
    return findings
