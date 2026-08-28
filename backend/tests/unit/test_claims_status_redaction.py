"""claims/service.py::get_disclosable_status — key selection + Level-2 financial-field
redaction (spec §13 Journey E, .claude/specs/phase-1-backend-spec.md decision 0.8).
"""

from datetime import datetime
from decimal import Decimal

from src.claims.constants import ClaimStage
from src.claims.models import MotorClaim
from src.claims.service import get_disclosable_status
from src.verification.constants import VerificationLevel


def _claim(stage: ClaimStage, settlement_amount: Decimal | None = Decimal("5000.00")) -> MotorClaim:
    # status_timestamp has only a server_default (populated on DB insert) — this test
    # constructs the object in memory without flushing, so it must be supplied explicitly.
    return MotorClaim(
        id="CLM-REDACT-TEST",
        policy_id="POL-X",
        customer_id="CUST-X",
        claim_stage=stage,
        language="en",
        settlement_amount=settlement_amount,
        customer_action_required=False,
        delay_flag=False,
        status_timestamp=datetime(2026, 8, 27, 12, 0, 0),
    )


def test_non_financial_stage_never_redacts():
    claim = _claim(ClaimStage.REPAIR_AUTHORIZED, settlement_amount=None)
    status = get_disclosable_status(claim, VerificationLevel.L0)
    assert status.settlement_amount is None
    assert status.claim_stage == ClaimStage.REPAIR_AUTHORIZED


def test_settlement_approved_redacted_below_l2():
    claim = _claim(ClaimStage.SETTLEMENT_APPROVED)
    for level in (VerificationLevel.L0, VerificationLevel.L1):
        status = get_disclosable_status(claim, level)
        assert status.settlement_amount is None


def test_settlement_approved_disclosed_at_l2():
    claim = _claim(ClaimStage.SETTLEMENT_APPROVED)
    status = get_disclosable_status(claim, VerificationLevel.L2)
    assert status.settlement_amount == Decimal("5000.00")


def test_payment_initiated_redacted_below_l2():
    claim = _claim(ClaimStage.PAYMENT_INITIATED)
    status = get_disclosable_status(claim, VerificationLevel.L1)
    assert status.settlement_amount is None


def test_payment_initiated_disclosed_at_l2():
    claim = _claim(ClaimStage.PAYMENT_INITIATED)
    status = get_disclosable_status(claim, VerificationLevel.L2)
    assert status.settlement_amount == Decimal("5000.00")


def test_claim_id_maps_from_motor_claim_id():
    claim = _claim(ClaimStage.CLAIM_REGISTERED, settlement_amount=None)
    status = get_disclosable_status(claim, VerificationLevel.L0)
    assert status.claim_id == "CLM-REDACT-TEST"
