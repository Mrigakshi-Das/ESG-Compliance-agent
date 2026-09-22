"""Guardrail #1 (no hallucinated data) and #2 (data conflict detection) and
#8 (data quality checks), applied to whatever a `get_*_data` tool already
returned.

This module does not re-detect missing/conflicting rows itself -- every
`app.tools.*` domain tool already does that via `app.tools._common.
resolve_rows` and reports it in its own `status`/`issues`/`raw_records`
fields (see that module's docstring). What this module adds is the part
that didn't exist before: turning that tool-level signal into a typed
`GuardrailStatus`, a `Provenance` record for every value, a structured
`DataConflict` object with per-source values (guardrail #2's exact
example shape), and outlier/duplicate detection for values a tool's own
row-resolution logic wouldn't catch (e.g. a single, un-duplicated row
whose value is a physically impossible negative number).
"""

from __future__ import annotations

from typing import Any

from app.compliance.data_quality import DataQualityReport
from app.guardrails.schemas import (
    ConflictingValue,
    DataConflict,
    DataQualityScore,
    GuardrailStatus,
    Provenance,
    ProvenancedValue,
)

# Fields that can never be negative in this domain -- a negative value here
# is impossible, not just unusual (guardrail #1 / TEST 5).
_NON_NEGATIVE_FIELDS = (
    "tonnes", "mwh", "gj", "tco2e", "m3", "days", "kcal_per_kg",
    "content_pct", "substitution_pct", "share", "humidity_pct", "rainfall_mm",
)
# Percentage-shaped fields must fall in [0, 100].
_PERCENT_FIELDS = ("_pct", "_share")


def _looks_non_negative(field_name: str) -> bool:
    return any(hint in field_name for hint in _NON_NEGATIVE_FIELDS)


def _looks_percent(field_name: str) -> bool:
    return any(field_name.endswith(hint) for hint in _PERCENT_FIELDS)


def tag_provenance(tool_name: str, result: dict[str, Any] | None = None) -> Provenance:
    """Build the Provenance record for a value that came back `status="ok"`
    from a registered tool -- guardrail #1's requirement that every
    important value trace to (1) a registered data tool, (2) a validated
    document, (3) an approved regulatory source, or (4) prior verified
    agent state. Tool calls are case (1)."""
    plant = (result or {}).get("plant")
    period = (result or {}).get("period")
    return Provenance(source=tool_name, source_type="registered_tool", plant=plant, period=period, verified=True)


def detect_anomalies(tool_name: str, values: dict[str, Any]) -> list[str]:
    """Return a list of human-readable anomaly descriptions for physically
    impossible values in an already-`status="ok"` result -- negative where
    negative is impossible, or a percentage outside [0, 100]. Empty list
    means no anomaly detected. This is intentionally conservative (only
    flags what is *provably* impossible, not merely surprising) so it never
    second-guesses a genuine, if unusual, real reading."""
    anomalies: list[str] = []
    for field_name, value in values.items():
        if not isinstance(value, (int, float)):
            continue
        if _looks_percent(field_name) and not (0 <= value <= 100):
            anomalies.append(f"{tool_name}.{field_name} = {value} is outside the valid 0-100% range.")
        elif _looks_non_negative(field_name) and value < 0:
            anomalies.append(f"{tool_name}.{field_name} = {value} is negative, which is not physically possible.")
    return anomalies


def classify_tool_result(tool_name: str, result: dict[str, Any] | None) -> GuardrailStatus:
    """The core guardrail #1/#2 classification for one tool call's result.

    - None (the tool raised ToolInputError/CalculationError, already
      caught by the orchestrator) -> DATA_MISSING, since no value exists.
    - status == "missing" -> DATA_MISSING.
    - status == "conflict" -> DATA_CONFLICT.
    - status == "ok" but the values contain a physically impossible number,
      or the tool flagged a duplicate-record issue -> DATA_ANOMALY.
    - status == "ok" and clean -> DATA_OK.
    """
    if not result:
        return "DATA_MISSING"
    if not isinstance(result, dict) or "status" not in result:
        return "DATA_OK"  # a calculation tool's bare result; not this module's concern

    status = result["status"]
    if status == "missing":
        return "DATA_MISSING"
    if status == "conflict":
        return "DATA_CONFLICT"

    if status == "ok":
        values = result.get("values") or {}
        if detect_anomalies(tool_name, values):
            return "DATA_ANOMALY"
        if any("identical" in issue and "logged more than once" in issue for issue in result.get("issues", [])):
            return "DATA_ANOMALY"  # duplicate record (TEST 11)
        return "DATA_OK"

    return "DATA_OK"


def build_data_conflict(tool_name: str, result: dict[str, Any], metric: str | None = None) -> DataConflict | None:
    """Build the structured DataConflict object (guardrail #2's exact
    output shape) from a tool result whose status is "conflict". Returns
    None if the result isn't actually a conflict -- callers should still
    check `classify_tool_result` first; this just does the extraction."""
    if not isinstance(result, dict) or result.get("status") != "conflict":
        return None

    raw_records = result.get("raw_records", [])
    metric_name = metric or tool_name.replace("get_", "").replace("_data", "")
    # One entry per record naming its primary metric value and source --
    # matches guardrail #2's example shape exactly. Full per-field detail
    # remains available in the tool's own raw_records for anyone who needs it.
    conflicting = [
        ConflictingValue(value=record.get(metric_name, record), source=record.get("source_system", "unknown_source"))
        for record in raw_records
    ]

    return DataConflict(
        metric=metric_name,
        values=conflicting,
        period=result.get("period"),
        severity="HIGH",
        impact=f"{metric_name.replace('_', ' ')} cannot be reliably used in downstream calculations while sources disagree.",
    )


def score_data_quality(report: DataQualityReport, total_domains: int = 5) -> DataQualityScore:
    """Turn the existing `app.compliance.data_quality.DataQualityReport`
    (already computed, not re-derived here) into the 0-100 numeric score
    guardrail #8 asks for. Methodology, stated plainly since this is a
    reliability *indicator*, never proof of compliance (see the module
    docstring on `DataQualityScore.overall`):

    - completeness: (domains with data) / (total domains checked) * 100
    - consistency:  100, minus 20 per conflicting domain and 15 per
                    duplicate-document issue, floored at 0
    - timeliness:   100, minus 10 per domain carrying a flagged issue
                    (stale/inconsistent readings), floored at 0 -- a proxy
                    for "how much of what we retrieved needed a caveat",
                    since this prototype has no live ingestion timestamps
                    to measure recency against directly.
    """
    completeness = round((total_domains - len(report.missing_domains)) / total_domains * 100, 1)
    consistency = max(0.0, 100 - 20 * len(report.conflicting_domains) - 15 * len(report.duplicate_documents))
    timeliness = max(0.0, 100 - 10 * len(report.flagged_issues))
    return DataQualityScore(completeness=completeness, consistency=round(consistency, 1), timeliness=round(timeliness, 1))
