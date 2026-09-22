"""Reads the `regulatory_targets` table -- the Phase 2 synthetic
placeholder (see DATA_DICTIONARY.md) with illustrative numeric targets for
the demo plants.

No longer the backend for `app/tools/regulations.py`'s `search_regulations`
-- Phase 4 replaced that with the real sourced knowledge base in
`app/regulations/{bee,sebi,environmental}.py`, which deliberately does
*not* hard-code a numeric target for Plant A/B/C (real BEE/SEBI targets are
entity-specific, gazette-named facts this prototype's fictional plants
cannot actually have). This table remains useful on its own terms: an
illustrative target a demo compliance run can feed to
`calculate_priority`/`compare_with_target` without pretending it's a real
regulatory figure.
"""

from typing import Any

from app.data.db import fetch_all


def load_regulatory_targets() -> list[dict[str, Any]]:
    return [dict(r) for r in fetch_all("regulatory_targets")]
