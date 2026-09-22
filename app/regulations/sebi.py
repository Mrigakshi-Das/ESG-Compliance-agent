"""SEBI requirements relevant to listed cement companies: Business
Responsibility and Sustainability Reporting (BRSR), BRSR Core, and its
assurance/value-chain provisions.

Content lives in app/regulations/sources/sebi.json, sourced from the 2021
BRSR circular, the 2023 BRSR Core circular, and the 2025 amendment circular
-- see that file and sources/registry.json for full citations.
"""

from app.regulations.loader import load_requirements_from
from app.regulations.schema import RegulatoryRequirement


def load_requirements() -> list[RegulatoryRequirement]:
    return load_requirements_from("sebi.json")
