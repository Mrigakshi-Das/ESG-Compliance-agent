"""Evaluates a requirement's `applicability_conditions` against known facts
about a specific plant/company -- and, critically, never guesses a fact it
wasn't given.

Several of the Phase 4 requirements attach at the *company* level (BRSR/
BRSR Core: does the plant's parent sit in the relevant market-cap band?) and
others at the *plant* level (PAT/CCTS: is this specific plant a gazette-
named Designated Consumer / obligated entity?). Neither is inferable from
production or emissions data -- they are facts that only exist in an
external registry (BEE's DC notification, SEBI's market-cap ranking, the
GEI Target Rules' Schedule). The Phase 2 synthetic dataset does not model
either fact for Plant A/B/C, and this module does not invent one: a caller
who supplies the fact gets a real verdict; a caller who doesn't gets an
honest "Cannot Determine", never a default assumption.

`known_facts` is a flat {criterion: bool} map -- the caller has already
resolved whatever comparison the requirement's `parameter` describes (e.g.
"is this company's market-cap rank within the top 500") into a yes/no. This
prototype does not parse `parameter` text into an automatic numeric
comparison; a future phase reading a real company registry could tighten
this without changing the interface below.
"""

from typing import Any, Literal

from app.regulations.schema import ApplicabilityCondition, RegulatoryRequirement

ApplicabilityVerdict = Literal["Applicable", "Not Applicable", "Cannot Determine"]


def evaluate_condition(
    condition: ApplicabilityCondition, known_facts: dict[str, Any]
) -> tuple[ApplicabilityVerdict, str]:
    if condition.criterion not in known_facts:
        return (
            "Cannot Determine",
            f"No fact supplied for '{condition.criterion}' ({condition.description}) -- "
            "this must be confirmed against the authoritative external record (a gazette "
            "Designated Consumer / obligated-entity list, or the parent company's listed "
            "market-cap rank); it cannot be inferred from plant operating data.",
        )
    value = known_facts[condition.criterion]
    if not isinstance(value, bool):
        return "Cannot Determine", f"Fact for '{condition.criterion}' must be True/False, got {value!r}."
    verdict: ApplicabilityVerdict = "Applicable" if value else "Not Applicable"
    return verdict, f"'{condition.criterion}' supplied as {value}."


def evaluate_requirement(
    requirement: RegulatoryRequirement, known_facts: dict[str, Any]
) -> dict[str, Any]:
    """Combine every condition's verdict: any 'Not Applicable' wins (the
    requirement definitely doesn't apply); otherwise any 'Cannot Determine'
    wins (at least one fact is missing); only if every condition resolves
    True is the requirement 'Applicable'.
    """
    if not requirement.applicability_conditions:
        return {
            "requirement_id": requirement.requirement_id,
            "verdict": "Applicable",
            "reasons": ["This requirement has no plant/company-specific applicability conditions."],
        }

    results = [evaluate_condition(c, known_facts) for c in requirement.applicability_conditions]
    verdicts = [v for v, _ in results]
    if "Not Applicable" in verdicts:
        overall: ApplicabilityVerdict = "Not Applicable"
    elif "Cannot Determine" in verdicts:
        overall = "Cannot Determine"
    else:
        overall = "Applicable"

    return {
        "requirement_id": requirement.requirement_id,
        "verdict": overall,
        "reasons": [reason for _, reason in results],
    }
