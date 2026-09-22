"""Unit tests for app.guardrails.regulatory_validation: guardrail #4.

Uses plain dicts with the same field names as
app.regulations.schema.RegulatoryRequirement so this stays independent of
what's actually in the live knowledge base right now.
"""

from app.guardrails.regulatory_validation import classify_regulatory_version, requires_human_review


def _req(**overrides):
    base = {
        "status": "Active",
        "superseded_or_amended_by": None,
        "effective_date": "2025-04-01",
        "last_reviewed": "2026-08-01",
    }
    base.update(overrides)
    return base


class TestClassifyRegulatoryVersion:
    def test_active_recently_reviewed_and_effective_is_current(self):
        status, reason = classify_regulatory_version(_req(), as_of="2026-09-12")
        assert status == "CURRENT"

    def test_superseded_status_is_outdated(self):
        status, reason = classify_regulatory_version(_req(status="Superseded"), as_of="2026-09-12")
        assert status == "OUTDATED"

    def test_superseded_by_field_alone_is_outdated_even_if_status_active(self):
        status, reason = classify_regulatory_version(_req(superseded_or_amended_by="BEE-PAT-CYCLE-VIII"), as_of="2026-09-12")
        assert status == "OUTDATED"
        assert "BEE-PAT-CYCLE-VIII" in reason

    def test_future_effective_date_is_future_effective(self):
        status, reason = classify_regulatory_version(_req(effective_date="2027-04-01"), as_of="2026-09-12")
        assert status == "FUTURE_EFFECTIVE"

    def test_draft_with_future_date_is_future_effective(self):
        status, reason = classify_regulatory_version(
            _req(status="Draft/Proposed", effective_date="2027-01-01"), as_of="2026-09-12",
        )
        assert status == "FUTURE_EFFECTIVE"

    def test_draft_with_no_confirmed_future_date_is_unknown(self):
        status, reason = classify_regulatory_version(
            _req(status="Draft/Proposed", effective_date="2025-04-01"), as_of="2026-09-12",
        )
        assert status == "UNKNOWN"

    def test_under_amendment_is_unknown(self):
        status, reason = classify_regulatory_version(_req(status="Under Amendment"), as_of="2026-09-12")
        assert status == "UNKNOWN"

    def test_stale_review_date_is_unknown_not_current(self):
        # Reviewed more than a year before the assessment date -- currency
        # cannot be assumed just because nothing else looks wrong.
        status, reason = classify_regulatory_version(_req(last_reviewed="2024-01-01"), as_of="2026-09-12")
        assert status == "UNKNOWN"
        assert "reviewed" in reason.lower()

    def test_existing_in_the_kb_is_not_enough_by_itself(self):
        # A record with an unrecognized/incomplete status string must not
        # default to CURRENT just because every date field looks fine.
        status, reason = classify_regulatory_version(_req(status="Repealed"), as_of="2026-09-12")
        assert status == "UNKNOWN"


class TestRequiresHumanReview:
    def test_current_does_not_require_review(self):
        assert requires_human_review("CURRENT") is False

    def test_outdated_requires_review(self):
        assert requires_human_review("OUTDATED") is True

    def test_unknown_requires_review(self):
        assert requires_human_review("UNKNOWN") is True

    def test_future_effective_requires_review(self):
        assert requires_human_review("FUTURE_EFFECTIVE") is True
