"""Placeholder module for other environmental/regulatory requirements
(e.g. state Pollution Control Board emission/effluent norms) as a future
module -- explicitly scoped out of the MVP per the project brief.

Loads structured records from `app/regulations/sources/environmental.json`
when populated.
"""

from app.regulations.loader import load_requirements_from
from app.regulations.schema import RegulatoryRequirement


def load_requirements() -> list[RegulatoryRequirement]:
    """Returns an empty list until sources/environmental.json is populated
    in a later phase (e.g. CPCB/state Pollution Control Board norms)."""
    return load_requirements_from("environmental.json")
