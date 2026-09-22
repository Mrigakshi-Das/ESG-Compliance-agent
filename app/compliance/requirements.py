"""Determines which regulatory requirements apply to a given plant, and
resolves each one's applicability verdict using Phase 4's evaluator and the
documented assumptions in `app.compliance.context`.

`plant` is accepted but not used to differentiate results: every documented
applicability fact in `DEMO_KNOWN_FACTS` applies uniformly across the demo's
three plants (see `test_same_result_for_every_plant`), and no requirement in
the Phase 4 KB has a plant-specific condition -- returning all 10
requirements (each carrying its own applicability verdict) is more
transparent than guessing a per-plant distinction the data doesn't support.
"""

from dataclasses import dataclass

from app.regulations.applicability import evaluate_requirement
from app.regulations.repository import all_requirements
from app.regulations.schema import RegulatoryRequirement
from app.compliance.context import DEMO_KNOWN_FACTS


@dataclass
class ApplicableRequirement:
    requirement: RegulatoryRequirement
    applicability_verdict: str  # "Applicable" | "Not Applicable" | "Cannot Determine"
    applicability_reasons: list[str]


def get_applicable_requirements(plant: str) -> list[ApplicableRequirement]:
    results = []
    for requirement in all_requirements():
        verdict = evaluate_requirement(requirement, DEMO_KNOWN_FACTS)
        results.append(ApplicableRequirement(
            requirement=requirement,
            applicability_verdict=verdict["verdict"],
            applicability_reasons=verdict["reasons"],
        ))
    return results
