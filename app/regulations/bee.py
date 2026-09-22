"""Bureau of Energy Efficiency requirements relevant to cement plants:
Perform Achieve and Trade (PAT), and the Carbon Credit Trading Scheme (CCTS)
/ GHG Emission Intensity (GEI) Target mechanism.

Content lives in app/regulations/sources/bee.json, sourced from BEE's PAT
program page, a PIB press release, and the primary Gazette text of the
Greenhouse Gases Emission Intensity Target Rules, 2025 -- see that file and
sources/registry.json for full citations.
"""

from app.regulations.loader import load_requirements_from
from app.regulations.schema import RegulatoryRequirement


def load_requirements() -> list[RegulatoryRequirement]:
    return load_requirements_from("bee.json")
