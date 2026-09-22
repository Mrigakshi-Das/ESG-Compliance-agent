"""Validation and row-resolution logic shared by every get_*_data tool.

Kept in one place so all six domain tools (production, energy, emissions,
water, waste, maintenance) apply the exact same rules for what counts as a
missing/duplicate/conflicting record -- a future seventh domain tool gets
this behavior for free instead of re-implementing it slightly differently.
"""

from typing import Any, Literal

from app.data.constants import PERIODS, PLANTS
from app.tools.errors import ToolInputError

RowStatus = Literal["empty", "ok", "duplicate", "conflict"]


def validate_plant(plant: str) -> None:
    if plant not in PLANTS:
        raise ToolInputError(f"Unknown plant {plant!r}. Expected one of {PLANTS}.")


def validate_period(period: str) -> None:
    if period not in PERIODS:
        raise ToolInputError(f"Unknown period {period!r}. Expected one of {PERIODS}.")


def resolve_rows(rows: list[dict[str, Any]], ignore_fields: tuple[str, ...] = ("source_system",)) -> RowStatus:
    """Classify a set of raw rows for the same (plant, period) key.

    - "empty": no rows at all -- the caller should report Data Missing.
    - "ok": exactly one row, or several rows that agree on every field
      except `ignore_fields` (a true duplicate -- same fact, logged twice).
    - "conflict": two or more rows that disagree on some field outside
      `ignore_fields` -- different systems/entries reporting different
      values for the same plant+period. Never resolved automatically.
    """
    if not rows:
        return "empty"
    if len(rows) == 1:
        return "ok"

    def comparable(row: dict[str, Any]) -> tuple:
        return tuple(sorted((k, v) for k, v in row.items() if k not in ignore_fields))

    first = comparable(rows[0])
    if all(comparable(r) == first for r in rows[1:]):
        return "ok"
    return "conflict"


def source_systems(rows: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for r in rows:
        s = r.get("source_system")
        if s and s not in seen:
            seen.append(s)
    return seen
