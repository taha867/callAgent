from src.claims.constants import FINANCIAL_STAGES, ClaimStage, get_status_criticality


def test_urgent_for_declined():
    assert get_status_criticality(ClaimStage.CLAIM_DECLINED) == "URGENT"


def test_action_required_for_additional_approval():
    assert get_status_criticality(ClaimStage.ADDITIONAL_APPROVAL_REQUIRED) == "ACTION_REQUIRED"


def test_action_required_for_additional_information():
    assert get_status_criticality(ClaimStage.ADDITIONAL_INFORMATION_REQUIRED) == "ACTION_REQUIRED"


def test_action_required_for_settlement_approved():
    assert get_status_criticality(ClaimStage.SETTLEMENT_APPROVED) == "ACTION_REQUIRED"


def test_normal_for_everything_else():
    for stage in ClaimStage:
        if stage in {
            ClaimStage.CLAIM_DECLINED,
            ClaimStage.ADDITIONAL_APPROVAL_REQUIRED,
            ClaimStage.ADDITIONAL_INFORMATION_REQUIRED,
            ClaimStage.SETTLEMENT_APPROVED,
        }:
            continue
        assert get_status_criticality(stage) == "NORMAL"


def test_financial_stages_are_settlement_and_payment_only():
    assert {ClaimStage.SETTLEMENT_APPROVED, ClaimStage.PAYMENT_INITIATED} == FINANCIAL_STAGES
