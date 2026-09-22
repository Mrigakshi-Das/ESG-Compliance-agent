"""Deterministic energy calculations. No LLM involvement."""

from app.calculations.errors import CalculationError


def calculate_energy_intensity(energy_consumption: float, production_tonnes: float) -> float:
    """Return energy consumed per tonne of production (specific energy
    consumption), in the caller-supplied energy unit per tonne.

    Raises CalculationError on non-positive production or negative energy
    consumption.
    """
    if production_tonnes <= 0:
        raise CalculationError(
            f"production_tonnes must be > 0 to compute energy intensity, got {production_tonnes}"
        )
    if energy_consumption < 0:
        raise CalculationError(f"energy_consumption cannot be negative, got {energy_consumption}")
    return energy_consumption / production_tonnes


def calculate_renewable_share(renewable_energy: float, total_energy: float) -> float:
    """Return renewable energy as a fraction (0-1) of total energy consumed.

    Not used by any Phase 3 tool yet -- left as a stub until a tool needs it.
    """
    raise NotImplementedError("Not required by any Phase 3 tool yet")
