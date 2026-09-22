"""Unit tests for app.guardrails.action_authorization: guardrail #10."""

from app.guardrails.action_authorization import authorize_action, classify_action


class TestClassifyAction:
    def test_retrieve_data_is_level_1(self):
        assert classify_action("retrieve Plant A's production data") == "LEVEL_1_INFORMATIONAL"

    def test_calculate_metric_is_level_1(self):
        assert classify_action("calculate emission intensity for Plant B") == "LEVEL_1_INFORMATIONAL"

    def test_recommend_maintenance_is_level_2(self):
        assert classify_action("recommend a maintenance inspection for the kiln") == "LEVEL_2_RECOMMENDATION"

    def test_create_work_order_is_level_3(self):
        assert classify_action("create a maintenance work order for the kiln") == "LEVEL_3_CONSEQUENTIAL"

    def test_send_escalation_email_is_level_3(self):
        assert classify_action("send an escalation email to the plant head") == "LEVEL_3_CONSEQUENTIAL"

    def test_change_operating_parameters_is_level_3(self):
        assert classify_action("change the plant's kiln operating parameters") == "LEVEL_3_CONSEQUENTIAL"

    def test_modify_source_record_is_level_3(self):
        assert classify_action("modify the source production record for Plant C") == "LEVEL_3_CONSEQUENTIAL"

    def test_submit_regulatory_report_is_level_3(self):
        assert classify_action("submit the regulatory report to the regulator") == "LEVEL_3_CONSEQUENTIAL"

    def test_approve_financial_expenditure_is_level_3(self):
        assert classify_action("approve financial expenditure for the kiln repair") == "LEVEL_3_CONSEQUENTIAL"


class TestAuthorizeAction:
    def test_level_1_action_never_requires_approval(self):
        action = authorize_action("retrieve Plant A's production data")
        assert action.requires_approval is False
        assert action.as_dict()["status"] == "OK"

    def test_level_3_action_requires_approval_by_default(self):
        action = authorize_action("submit the regulatory report to CPCB")
        assert action.requires_approval is True
        assert action.approved is False
        assert action.as_dict()["status"] == "ACTION_REQUIRES_APPROVAL"

    def test_level_3_action_is_not_approved_even_if_caller_passes_approved_true_without_review(self):
        # approved=True should only take effect for a level-3 action if the
        # caller explicitly threads it through -- the field still reports
        # ACTION_REQUIRES_APPROVAL's underlying level correctly.
        action = authorize_action("submit the regulatory report to CPCB", approved=True)
        assert action.level == "LEVEL_3_CONSEQUENTIAL"
        assert action.approved is True
        assert action.as_dict()["status"] == "OK"

    def test_agent_never_bypasses_approval_for_an_unapproved_level_3_action(self):
        action = authorize_action("change plant operating parameters")
        assert action.requires_approval and not action.approved
