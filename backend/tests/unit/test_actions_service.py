"""actions/service.py — idempotent create_action/create_escalation/schedule_callback,
task 7. Mirrors tests/unit/test_idempotency.py's pattern for testing idempotent() callers.
"""

from datetime import datetime

from src.actions.constants import ActionCode
from src.actions.service import create_action, create_escalation, schedule_callback
from src.claims.constants import ClaimStage
from src.claims.models import MotorClaim, MotorPolicy
from src.customers.models import Customer


async def _seed_claim(db_session, *, suffix: str) -> str:
    customer_id = f"CUST-ACT-{suffix}"
    db_session.add(Customer(id=customer_id, full_name="x", phone_e164="+1"))
    await db_session.flush()
    db_session.add(
        MotorPolicy(
            id=f"POL-ACT-{suffix}",
            customer_id=customer_id,
            policy_number="P1",
            vehicle_plate="X",
            vehicle_make_model="Y",
        )
    )
    await db_session.flush()
    claim_id = f"CLM-ACT-{suffix}"
    db_session.add(
        MotorClaim(
            id=claim_id,
            policy_id=f"POL-ACT-{suffix}",
            customer_id=customer_id,
            claim_stage=ClaimStage.DOCUMENTS_PENDING,
            language="en",
        )
    )
    await db_session.flush()
    return claim_id


async def test_create_action_succeeds(db_session):
    claim_id = await _seed_claim(db_session, suffix="1")
    result = await create_action(
        db_session,
        key=f"{claim_id}-ACTION-1",
        correlation_id=claim_id,
        claim_id=claim_id,
        action_code=ActionCode.DOCUMENT_STATUS_DISPUTE,
        summary="Customer disputes missing police report",
    )
    assert result["claim_id"] == claim_id
    assert result["action_code"] == ActionCode.DOCUMENT_STATUS_DISPUTE.value
    assert result["status"] == "OPEN"


async def test_create_action_is_idempotent_on_replay(db_session):
    claim_id = await _seed_claim(db_session, suffix="2")
    key = f"{claim_id}-ACTION-1"
    first = await create_action(
        db_session,
        key=key,
        correlation_id=claim_id,
        claim_id=claim_id,
        action_code=ActionCode.CLAIM_DELAY_ESCALATION,
        summary="delay escalation",
    )
    second = await create_action(
        db_session,
        key=key,
        correlation_id=claim_id,
        claim_id=claim_id,
        action_code=ActionCode.CLAIM_DELAY_ESCALATION,
        summary="delay escalation",
    )
    assert first["id"] == second["id"]


async def test_create_escalation_succeeds(db_session):
    result = await create_escalation(
        db_session,
        key="CALL-ESC-1-ACTION-1",
        correlation_id="CALL-ESC-1",
        call_id="CALL-ESC-1",
        reason="CUSTOMER_REQUESTED_HUMAN",
        context_snapshot={"verification_level": "L1", "claim_id": "CLM-X"},
    )
    assert result["call_id"] == "CALL-ESC-1"
    assert result["reason"] == "CUSTOMER_REQUESTED_HUMAN"


async def test_schedule_callback_succeeds(db_session):
    customer_id = "CUST-CB-1"
    db_session.add(Customer(id=customer_id, full_name="x", phone_e164="+1"))
    await db_session.flush()

    result = await schedule_callback(
        db_session,
        key="CALL-CB-1-ACTION-1",
        correlation_id="CALL-CB-1",
        customer_id=customer_id,
        callback_window_start=datetime(2026, 8, 26, 18, 0, 0),
        callback_window_end=datetime(2026, 8, 26, 20, 0, 0),
        reason="CUSTOMER_DRIVING",
    )
    assert result["customer_id"] == customer_id
    assert result["reason"] == "CUSTOMER_DRIVING"
    assert result["status"] == "SCHEDULED"
