"""Guardrail #6: deterministic calculations.

The LLM (when the optional `ANTHROPIC_API_KEY` path is active) is never
asked to compute a number itself -- it can only request a tool call, and
`app.calculations.*` already raises `CalculationError` on non-positive
production, negative emissions, a zero target, or an out-of-range factor
(see e.g. `app.calculations.emissions.calculate_emission_intensity`'s own
docstring). This module does not re-validate those same rules a second
time; it wraps *any* such call into one structured result shape
(guardrail #6's `{result, formula, inputs, units, source_provenance,
validation_status}`), and adds the one check the calculation functions
themselves cannot make on their own: whether the inputs' own provenance
is even compatible (same plant, same reporting period) before the
arithmetic runs at all.
"""

from __future__ import annotations

from typing import Any, Callable

from app.calculations.errors import CalculationError
from app.guardrails.schemas import CalculationResult, Provenance


def check_input_compatibility(inputs: dict[str, Provenance]) -> str | None:
    """Return a rejection reason if two or more inputs disagree on plant or
    period (an "incompatible periods" case guardrail #6 calls out
    explicitly) -- e.g. combining this quarter's emissions with last
    quarter's production would silently produce a meaningless intensity.
    Returns None when everything lines up (or too few inputs carry
    plant/period to compare)."""
    plants = {p.plant for p in inputs.values() if p.plant}
    periods = {p.period for p in inputs.values() if p.period}
    if len(plants) > 1:
        return f"Inputs come from different plants ({sorted(plants)}) -- cannot combine them in one calculation."
    if len(periods) > 1:
        return f"Inputs come from different reporting periods ({sorted(periods)}) -- cannot combine them in one calculation."
    return None


def safe_calculate(
    fn: Callable[..., float],
    formula: str,
    units: str,
    inputs: dict[str, Any],
    provenance: dict[str, Provenance],
) -> CalculationResult:
    """Run a deterministic calculation function under guardrail #6's
    structured contract.

    `inputs` are the actual keyword arguments passed to `fn` (e.g.
    `{"emissions_tco2e": 256663.7, "production_tonnes": 452000.0}`);
    `provenance` maps (a subset of) those same argument names to where each
    value came from, so an incompatible-period combination is caught
    *before* the arithmetic runs, and every PASSED result carries full
    source provenance for guardrail #14's output validation to check.
    """
    incompatibility = check_input_compatibility(provenance)
    if incompatibility:
        return CalculationResult(
            result=None, formula=formula, inputs=inputs, units=units,
            source_provenance=[p.as_dict() for p in provenance.values()],
            validation_status="BLOCKED", rejection_reason=incompatibility,
        )

    try:
        result = fn(**inputs)
    except CalculationError as exc:
        return CalculationResult(
            result=None, formula=formula, inputs=inputs, units=units,
            source_provenance=[p.as_dict() for p in provenance.values()],
            validation_status="BLOCKED", rejection_reason=str(exc),
        )

    return CalculationResult(
        result=result, formula=formula, inputs=inputs, units=units,
        source_provenance=[p.as_dict() for p in provenance.values()],
        validation_status="PASSED",
    )
