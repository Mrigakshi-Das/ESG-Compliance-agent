"""Exception for a calculation called with a numerically invalid input
(non-positive production denominator, non-numeric target, out-of-range
priority factor, ...). Deliberately a hard failure -- a calculation tool
must never substitute a guessed or clamped value for an invalid one.
"""


class CalculationError(ValueError):
    pass
