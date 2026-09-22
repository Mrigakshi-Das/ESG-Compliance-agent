"""Unit tests for app.guardrails.source_validation: guardrail #3."""

from app.guardrails.source_validation import can_support_compliance_conclusion, classify_source


class TestClassifySource:
    def test_bee_is_tier_1(self):
        assert classify_source(authority="BEE") == "TIER_1_AUTHORITATIVE"

    def test_sebi_is_tier_1(self):
        assert classify_source(authority="SEBI") == "TIER_1_AUTHORITATIVE"

    def test_cpcb_is_tier_1(self):
        assert classify_source(authority="CPCB") == "TIER_1_AUTHORITATIVE"

    def test_government_notification_description_is_tier_1(self):
        assert classify_source(source_description="Government notification G.S.R. 234(E)") == "TIER_1_AUTHORITATIVE"

    def test_internal_sop_is_tier_2(self):
        assert classify_source(source_description="Internal SOP for kiln operations") == "TIER_2_ORGANIZATION"

    def test_consulting_report_is_tier_3(self):
        assert classify_source(source_description="McKinsey industry consulting report on cement decarbonization") == "TIER_3_SECONDARY"

    def test_news_article_is_tier_3(self):
        assert classify_source(source_description="News article about BEE targets") == "TIER_3_SECONDARY"

    def test_unrecognized_source_defaults_to_tier_3_not_tier_1(self):
        # An unknown source must never be silently assumed authoritative.
        assert classify_source(authority="Some Random Blog") == "TIER_3_SECONDARY"

    def test_empty_source_defaults_to_tier_3(self):
        assert classify_source() == "TIER_3_SECONDARY"


class TestCanSupportComplianceConclusion:
    def test_tier_1_can_support_conclusion(self):
        assert can_support_compliance_conclusion("TIER_1_AUTHORITATIVE") is True

    def test_tier_2_can_support_conclusion(self):
        assert can_support_compliance_conclusion("TIER_2_ORGANIZATION") is True

    def test_tier_3_cannot_support_conclusion_alone(self):
        assert can_support_compliance_conclusion("TIER_3_SECONDARY") is False
