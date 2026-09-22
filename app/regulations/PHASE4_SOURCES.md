# Phase 4 Source Verification Notes

How each regulation in the knowledge base was researched, what was
confirmed against a primary source versus a secondary summary, and what a
future phase should re-verify. The structured citation data itself lives in
[sources/registry.json](sources/registry.json) (one entry per underlying
document) and each requirement record's `source_id` field; this file is the
narrative trail behind it.

## BEE PAT

Confirmed via BEE's own program page (beeindia.gov.in) and a PIB press
release: cement has been covered since PAT Cycle I (2012); PAT Cycle VII
covered FY2022-23 to FY2024-25 (509 DCs, ~6.627 MTOE aggregate target). The
current-cycle cement threshold (historically >30,000 toe/year) and the
gazette-notified Designated Consumer list were **not** independently
re-verified against a live cycle notification in this session — a later
cycle (VIII) may already be in force. Confidence: **Medium** on the cycle
specifics; the mechanism itself (DC designation → SEC target → ESCert
trade) is well-documented and higher confidence.

## BEE CCTS / GHG Emission Intensity (GEI) Target Rules

This is the best-sourced part of the knowledge base. The primary Gazette
text was located and read in full in this session:

> Ministry of Environment, Forest and Climate Change, Notification, New
> Delhi, 16 April 2025, **G.S.R. 234(E)** — draft Greenhouse Gases Emission
> Intensity Target Rules, 2025, issued under sections 3, 6 and 25 of the
> Environment (Protection) Act, 1986, to operationalize the Carbon Credit
> Trading Scheme, 2023 (notified vide S.O. 2825(E), 28 June 2023, under
> section 14(w) of the Energy Conservation Act, 2001). F.No.
> HSM-12/114/2022, signed Nameeta Prasad, Joint Secretary.

This draft's Schedule names 282 obligated entities across four sectors
(aluminium, cement, chlor-alkali, pulp & paper); 186 of them are cement
units, each with a baseline (FY2023-24) GHG emission intensity and
compliance-year targets for FY2025-26 and FY2026-27. The illustrative range
quoted in BEE-CCTS-002 (e.g. Composite/blended cement ~0.32-0.51 tCO2e/t,
Ordinary Portland Cement ~0.73-1.10 tCO2e/t, grinding-only units
~0.001-0.15 tCO2e/t) was computed directly from that Schedule's own
baseline/target columns, not from a secondary summary.

**What's not confirmed**: this is the *draft* (60-day comment window from
16 April 2025). Secondary sources report a final version, G.S.R. 739(E),
notified 8 October 2025, and a further amendment effective 13 January
2026 — neither final text was independently re-read in this session, so
the final per-entity figures could differ from the draft's. Confidence:
**High** for the mechanism, legal basis, and the illustrative range (all
read from primary text); the exact final numbers should be re-confirmed
against G.S.R. 739(E) before being relied on for a real compliance
determination.

**None of the demo plants (Plant A/B/C) appear in the real Schedule** —
they're fictional. The knowledge base is built to never assume otherwise;
see `app/regulations/applicability.py`.

## SEBI BRSR

Circular No. SEBI/HO/CFD/CMD-2/P/CIR/2021/562 (10 May 2021) was located
directly on sebi.gov.in, though the fetched page exposed only header
metadata, not the full operative text. Applicability (top 1,000 listed
entities by market cap, mandatory from FY2022-23, voluntary for FY2021-22)
was corroborated by SEBI's own press release of the same date. Confidence:
**High**.

## SEBI BRSR Core

Circular No. SEBI/HO/CFD/CFD-SEC-2/P/CIR/2023/122 (12 July 2023) was
located via a legal-archive mirror (the primary text is on sebi.gov.in but
was not directly fetched in this session). The assurance glide path (top
150 FY23-24 → top 250 FY24-25 → top 500 FY25-26 → top 1,000 FY26-27) and
the value-chain provisions (partners ≥2% of purchases/sales, capped at 75%
coverage) are corroborated across multiple independent secondary sources.

A subsequent amendment, Circular No. SEBI/HO/CFD/CFD-PoD-1/P/CIR/2025/42
(28 March 2025), was also researched: it introduces "assessment" as an
alternative to formal "assurance," and defers value-chain reporting by one
financial year. Confidence: **High** for the 2023 circular's core
provisions; **Medium** for the 2025 amendment's exact scope, since it was
built from secondary summaries rather than the primary circular text.

## What a real deployment would need that this prototype doesn't have

1. **A live sync to BEE's cycle-specific Designated Consumer notifications**
   and the GEI Target Rules' Schedule (as amended) — both are closed, named
   lists that change over time; this KB stores the *mechanism*, not a
   live copy of either list.
2. **A company/ownership model** linking each plant to its parent listed
   entity and that entity's market-cap rank — BRSR/BRSR Core applicability
   attaches to the company, not the plant, and the Phase 2 synthetic
   dataset has no such model. `app/regulations/applicability.py` is built
   to say "Cannot Determine" rather than guess this.
3. **Confirmation of the finalized GEI Target Rules** (G.S.R. 739(E) and
   its 13-Jan-2026 amendment) against primary text, since only the draft
   was read in full here.
