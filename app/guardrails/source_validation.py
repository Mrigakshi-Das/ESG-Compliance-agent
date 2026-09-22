"""Guardrail #3: authoritative regulatory sources.

Classifies a source into the three-tier hierarchy the brief specifies, and
enforces the rule that follows from it: a Tier 3 (secondary) source may
inform context, but a compliance *conclusion* must never rest on one alone.

Every regulatory record actually in this project's knowledge base
(`app/regulations/sources/`) already names its `authority` (BEE, SEBI,
CPCB/MoEFCC via the environmental module) and is Tier 1 by construction --
this module doesn't change what's in the KB, it adds the classification
step so a *future* source (an internal SOP, a consultant report) has a
defined, enforced tier instead of being silently treated as equally
authoritative.
"""

from __future__ import annotations

from app.guardrails.schemas import SourceTier

_TIER_1_AUTHORITIES = {
    "bee", "sebi", "cpcb", "moefcc",
    "bureau of energy efficiency",
    "securities and exchange board of india",
    "central pollution control board",
    "ministry of environment, forest and climate change",
}
_TIER_1_KEYWORDS = ("government notification", "gazette", "official circular", "regulatory circular")

_TIER_2_KEYWORDS = (
    "internal esg policy", "internal policy", "internal sop", "standard operating procedure",
    "approved compliance document", "company policy",
)

_TIER_3_KEYWORDS = (
    "consulting report", "consultant", "industry report", "news article", "news", "academic", "research paper", "blog",
)


def classify_source(authority: str | None = None, source_description: str | None = None) -> SourceTier:
    """Classify a source into TIER_1_AUTHORITATIVE / TIER_2_ORGANIZATION /
    TIER_3_SECONDARY. `authority` is the authority name as every
    `RegulatoryRequirement.authority` field in this KB actually carries it
    -- a real record reads e.g. "Bureau of Energy Efficiency (BEE),
    Ministry of Power" or "Ministry of Environment, Forest and Climate
    Change (MoEFCC) / Bureau of Energy Efficiency (BEE)" for a jointly
    administered rule, never the bare short name alone -- so this checks
    whether a known Tier 1 authority name appears in the field (a
    substring match), not an exact match against a short label. Unlike
    `source_description` below (free text that might merely *mention* an
    authority in passing, e.g. a news article), `authority` is a
    structured field that only ever names who actually issued the
    regulation, so a substring match here carries no false-positive risk.
    `source_description` is free text describing a source when no
    dedicated authority field applies (e.g. an evidence document's own
    label). Unrecognized sources are conservatively classified Tier 3 --
    an unknown source is never assumed authoritative."""
    authority_l = (authority or "").strip().lower()
    if authority_l and any(a in authority_l for a in _TIER_1_AUTHORITIES):
        return "TIER_1_AUTHORITATIVE"

    desc_l = (source_description or "").strip().lower()
    # Tier 3 checked first: an explicit "news article"/"consulting report"
    # label is a stronger, more specific signal than an authority name that
    # merely happens to be *mentioned* in the description (e.g. "a news
    # article about BEE targets" is Tier 3, not Tier 1, even though "BEE"
    # appears in the text) -- only a genuine authority-issued source, named
    # via the dedicated `authority` field or an explicit official-source
    # phrase, is Tier 1.
    if any(k in desc_l for k in _TIER_3_KEYWORDS):
        return "TIER_3_SECONDARY"
    if any(k in desc_l for k in _TIER_2_KEYWORDS):
        return "TIER_2_ORGANIZATION"
    if any(k in desc_l for k in _TIER_1_KEYWORDS):
        return "TIER_1_AUTHORITATIVE"

    # No authority and no recognizable description at all -- can't even
    # place it at Tier 3 with confidence; still returned as Tier 3 (never
    # assumed authoritative), but callers should treat this as a strong
    # human-review signal, not a normal secondary source.
    return "TIER_3_SECONDARY"


def can_support_compliance_conclusion(tier: SourceTier) -> bool:
    """Guardrail #3's central rule: Tier 3 alone must never be the sole
    basis for a compliance conclusion. Tier 1 and Tier 2 sources can."""
    return tier in ("TIER_1_AUTHORITATIVE", "TIER_2_ORGANIZATION")
