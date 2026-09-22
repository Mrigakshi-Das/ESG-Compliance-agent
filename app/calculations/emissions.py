"""Deterministic emissions calculations. No LLM involvement."""

from app.calculations.errors import CalculationError


def calculate_emission_intensity(emissions_tco2e: float, production_tonnes: float) -> float:
    """Return tCO2e per tonne of production.

    Raises CalculationError on non-positive production or negative
    emissions -- never silently returns 0 or infinity, and never guesses a
    production figure to make the division work.
    """
    if production_tonnes <= 0:
        raise CalculationError(
            f"production_tonnes must be > 0 to compute emission intensity, got {production_tonnes}"
        )
    if emissions_tco2e < 0:
        raise CalculationError(f"emissions_tco2e cannot be negative, got {emissions_tco2e}")
    return emissions_tco2e / production_tonnes
