"""Loads a JSON source file under `app/regulations/sources/` into
`RegulatoryRequirement` instances.

Kept separate from each authority module so bee.py/sebi.py/environmental.py
stay one-line wrappers naming their own JSON file -- the actual JSON ->
dataclass conversion (including tuple coercion for the list fields) lives
here once.
"""

import json
from pathlib import Path

from app.regulations.schema import ApplicabilityCondition, RegulatoryRequirement

SOURCES_DIR = Path(__file__).resolve().parent / "sources"


def load_requirements_from(filename: str) -> list[RegulatoryRequirement]:
    path = SOURCES_DIR / filename
    if not path.exists():
        return []
    records = json.loads(path.read_text(encoding="utf-8"))
    return [_to_requirement(r) for r in records]


def _to_requirement(record: dict) -> RegulatoryRequirement:
    conditions = tuple(
        ApplicabilityCondition(
            level=c["level"],
            criterion=c["criterion"],
            description=c["description"],
            parameter=c.get("parameter"),
        )
        for c in record["applicability_conditions"]
    )
    return RegulatoryRequirement(
        requirement_id=record["requirement_id"],
        regulation=record["regulation"],
        authority=record["authority"],
        industry=record["industry"],
        requirement_description=record["requirement_description"],
        applicability=record["applicability"],
        applicability_conditions=conditions,
        metric=record["metric"],
        unit=record["unit"],
        target=record["target"],
        reporting_period=record["reporting_period"],
        reporting_frequency=record["reporting_frequency"],
        required_evidence=tuple(record["required_evidence"]),
        effective_date=record["effective_date"],
        source_id=record["source_id"],
        source_title=record["source_title"],
        source_url=record["source_url"],
        source_date=record["source_date"],
        last_reviewed=record["last_reviewed"],
        confidence=record["confidence"],
        status=record["status"],
        version=record["version"],
        superseded_or_amended_by=record.get("superseded_or_amended_by"),
        notes=record.get("notes", ""),
    )


def load_source_registry() -> list[dict]:
    # Filename kept short deliberately: this project's scratch-workspace
    # path is already long, and "source_registry.json" pushed the full
    # resolved path past Windows' 260-character MAX_PATH, causing silent
    # FileNotFoundErrors despite the file existing and appearing in
    # directory listings.
    path = SOURCES_DIR / "registry.json"
    return json.loads(path.read_text(encoding="utf-8"))
