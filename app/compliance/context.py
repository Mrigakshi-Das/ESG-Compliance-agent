"""Documented, prototype-only applicability facts for the demo plants.

`app.regulations.applicability` (Phase 4) refuses to guess a fact it wasn't
given -- correctly, since PAT Designated Consumer status, CCTS Obligated
Entity status, and a company's SEBI market-cap rank are all facts that only
exist in a real external registry (a BEE/MoEFCC gazette list, or a stock
exchange's market-cap ranking), none of which the Phase 2 synthetic dataset
models. Left with nothing supplied, every applicability condition resolves
"Cannot Determine" and the compliance engine correctly reports
`Human Review Required` for all of PAT and CCTS.

For BRSR/BRSR Core specifically, this module makes one explicit,
clearly-labeled assumption so the demonstration produces real
Compliant/Potential-Gap/Evidence-* findings instead of "Human Review
Required" across the entire knowledge base: that the plants' parent listed
entity is large enough to fall within SEBI's applicable population,
including the assurance glide-path band reached by FY2025-26. This is an
assumption made for this prototype's demonstration purposes, not a
verified fact -- exactly the kind of thing Phase 1's "if information is
missing, make a reasonable assumption and display it clearly" principle
calls for, and it is surfaced in every assessment's Assumptions section
(see `app.compliance.engine`).

PAT and CCTS deliberately get NO such assumption: unlike a market-cap
rank, gazette-named Designated Consumer / Obligated Entity status is not a
"plausible for a company this size" kind of fact -- guessing it either way
would be exactly the "hard-coded regulatory assumption without identifying
a source" the project brief prohibits.
"""

DEMO_KNOWN_FACTS: dict[str, bool] = {
    "listed_entity_market_cap_rank": True,
    "reporting_period": True,
}

ASSUMPTION_NOTES: tuple[str, ...] = (
    "Assumed the plants' parent listed entity falls within SEBI's applicable "
    "market-capitalization population for BRSR/BRSR Core, including the "
    "assurance glide-path band reached by FY2025-26 -- not verified against "
    "an actual company registry (the synthetic dataset has no company/"
    "ownership model). This assumption applies uniformly to all three demo "
    "plants.",
    "PAT Designated Consumer status and CCTS Obligated Entity status are "
    "NOT assumed either way -- both require a name match against a real "
    "BEE/MoEFCC gazette list this prototype does not have, so PAT/CCTS "
    "requirements are marked Human Review Required rather than guessed.",
)
