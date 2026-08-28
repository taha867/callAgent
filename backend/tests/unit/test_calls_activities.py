"""calls/activities.py — real activities, called directly as plain functions (no Temporal
worker needed for this batch, per .claude/specs/phase-1-backend-implementation-plan.md
Batch 10). Uses db_session_committed since every activity opens its own session via
get_session_factory(), same as tests/integration/test_phase0_e2e.py's existing pattern for
record_audit_event.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from src.actions.constants import ActionCode
from src.calls import activities as calls_activities
from src.calls.constants import CallState
from src.customers.service import hash_factor_value

_NOW = datetime(2026, 8, 27, 12, 0, 0)


async def _seed_full_call(db, *, suffix: str, factor_value: str = "1990") -> dict:
    from src.claims.constants import ClaimStage
    from src.claims.models import MotorClaim, MotorPolicy
    from src.customers.models import Customer, CustomerAuthFactor

    customer_id = f"CUST-ACT-{suffix}"
    db.add(Customer(id=customer_id, full_name="x", phone_e164=f"+9715{suffix}"))
    await db.flush()
    db.add(
        CustomerAuthFactor(
            id=f"FACTOR-ACT-{suffix}",
            customer_id=customer_id,
            factor_type="BIRTH_MONTH_YEAR",
            factor_value_hash=hash_factor_value(factor_value),
        )
    )
    db.add(
        MotorPolicy(
            id=f"POL-ACT-{suffix}",
            customer_id=customer_id,
            policy_number="P1",
            vehicle_plate="X",
            vehicle_make_model="Y",
        )
    )
    await db.flush()
    claim_id = f"CLM-ACT-{suffix}"
    db.add(
        MotorClaim(
            id=claim_id,
            policy_id=f"POL-ACT-{suffix}",
            customer_id=customer_id,
            claim_stage=ClaimStage.REPAIR_AUTHORIZED,
            language="en",
            approved_customer_message_key="MOTOR_REPAIR_AUTHORIZED",
        )
    )
    await db.commit()
    return {"customer_id": customer_id, "claim_id": claim_id}


async def test_create_call_attempt(db_session_committed):
    seeded = await _seed_full_call(db_session_committed, suffix="1")
    call_id = await calls_activities.create_call_attempt(
        calls_activities.CreateCallAttemptInput(
            call_id="CALL-ACT-1",
            customer_id=seeded["customer_id"],
            claim_id=seeded["claim_id"],
            call_job_id=None,
            attempt_number=1,
            attempted_at=_NOW,
        )
    )
    assert call_id == "CALL-ACT-1"


async def test_classify_answer_returns_simulated_result():
    result = await calls_activities.classify_answer(
        calls_activities.ClassifyAnswerInput(call_id="X", simulated_answer_result="NO_ANSWER")
    )
    assert result == "NO_ANSWER"


async def test_create_and_update_call_session(db_session_committed):
    seeded = await _seed_full_call(db_session_committed, suffix="2")
    call_id = await calls_activities.create_call_attempt(
        calls_activities.CreateCallAttemptInput(
            call_id="CALL-ACT-2",
            customer_id=seeded["customer_id"],
            claim_id=seeded["claim_id"],
            call_job_id=None,
            attempt_number=1,
            attempted_at=_NOW,
        )
    )
    session_id = await calls_activities.create_call_session(
        calls_activities.CreateCallSessionInput(
            call_attempt_id=call_id, state=CallState.RIGHT_PARTY_CHECK
        )
    )
    await calls_activities.update_call_session(
        calls_activities.UpdateCallSessionInput(
            call_session_id=session_id, right_party_confirmed=True, state=CallState.AUTHENTICATION
        )
    )

    from src.calls.models import CallSession

    async with calls_activities.get_session_factory()() as session:
        row = await session.get(CallSession, session_id)
        assert row.right_party_confirmed is True
        assert row.state == CallState.AUTHENTICATION


async def test_verify_level1_activity(db_session_committed):
    from src.calls.models import CallAttempt, CallSession

    seeded = await _seed_full_call(db_session_committed, suffix="3")
    async with calls_activities.get_session_factory()() as session, session.begin():
        session.add(
            CallAttempt(
                id="CALL-ACT-3", customer_id=seeded["customer_id"], claim_id=seeded["claim_id"]
            )
        )
        await session.flush()
        session.add(
            CallSession(
                id="SESS-ACT-3", call_attempt_id="CALL-ACT-3", state=CallState.AUTHENTICATION
            )
        )

    result = await calls_activities.verify_level1(
        calls_activities.VerifyLevel1Input(
            call_session_id="SESS-ACT-3",
            customer_id=seeded["customer_id"],
            factor_type="BIRTH_MONTH_YEAR",
            supplied_value="1990",
            now=_NOW,
        )
    )
    assert result.outcome == "MATCH"
    assert result.attempts_so_far == 1


async def test_get_configured_auth_factor_type(db_session_committed):
    seeded = await _seed_full_call(db_session_committed, suffix="4")
    factor_type = await calls_activities.get_configured_auth_factor_type(
        calls_activities.GetAuthFactorTypeInput(customer_id=seeded["customer_id"])
    )
    assert factor_type == "BIRTH_MONTH_YEAR"


async def test_send_and_verify_otp_activity(db_session_committed):
    from src.calls.models import CallAttempt, CallSession

    seeded = await _seed_full_call(db_session_committed, suffix="5")
    async with calls_activities.get_session_factory()() as session, session.begin():
        session.add(
            CallAttempt(
                id="CALL-ACT-5", customer_id=seeded["customer_id"], claim_id=seeded["claim_id"]
            )
        )
        await session.flush()
        session.add(
            CallSession(
                id="SESS-ACT-5", call_attempt_id="CALL-ACT-5", state=CallState.AUTHENTICATION
            )
        )

    sent = await calls_activities.send_otp(
        calls_activities.SendOtpInput(
            call_session_id="SESS-ACT-5", phone_e164="+971500000099", now=_NOW
        )
    )
    assert sent.sent_count == 1

    from src.verification.adapters.otp_delivery.log_only import get_last_sent_code_for_testing

    code = get_last_sent_code_for_testing("+971500000099")
    assert code is not None

    verified = await calls_activities.verify_otp(
        calls_activities.VerifyOtpInput(
            challenge_id=sent.challenge_id, supplied_code=code, now=_NOW
        )
    )
    assert verified.status == "VERIFIED"


async def test_deliver_status_activity(db_session_committed):
    seeded = await _seed_full_call(db_session_committed, suffix="6")
    result = await calls_activities.deliver_status(
        calls_activities.DeliverStatusInput(claim_id=seeded["claim_id"], verification_level="L1")
    )
    assert result is not None
    assert result.approved_customer_message_key == "MOTOR_REPAIR_AUTHORIZED"


async def test_deliver_status_activity_returns_none_for_missing_claim(db_session_committed):
    result = await calls_activities.deliver_status(
        calls_activities.DeliverStatusInput(claim_id="CLM-DOES-NOT-EXIST", verification_level="L0")
    )
    assert result is None


async def test_with_runtime_recovery_records_failure_and_reraises(
    db_session_committed, monkeypatch
):
    monkeypatch.setattr(calls_activities.settings, "BACKEND_SOFT_WAIT_MS", 1)

    class _SlowInput:
        call_id = "CALL-TIMEOUT-TEST"

    @calls_activities.with_runtime_recovery(component="BACKEND", failure_type="BACKEND_TIMEOUT")
    async def _slow(inp):
        import asyncio

        await asyncio.sleep(1)
        return "never gets here"

    with pytest.raises(TimeoutError):
        await _slow(_SlowInput())

    from src.audit.models import RuntimeFailureEvent

    async with calls_activities.get_session_factory()() as session:
        result = await session.execute(
            select(RuntimeFailureEvent).where(RuntimeFailureEvent.call_id == "CALL-TIMEOUT-TEST")
        )
        row = result.scalars().first()
        assert row is not None
        assert row.component == "BACKEND"
        assert row.failure_type == "BACKEND_TIMEOUT"
        assert row.recovery_action == "SAFE_TERMINATION"


async def test_create_action_activity(db_session_committed):
    seeded = await _seed_full_call(db_session_committed, suffix="7")
    result = await calls_activities.create_action(
        calls_activities.CreateActionInput(
            key=f"{seeded['claim_id']}-ACTION-1",
            correlation_id=seeded["claim_id"],
            claim_id=seeded["claim_id"],
            action_code=ActionCode.DOCUMENT_STATUS_DISPUTE.value,
            summary="dispute",
        )
    )
    assert result["action_code"] == ActionCode.DOCUMENT_STATUS_DISPUTE.value


async def test_create_escalation_activity(db_session_committed):
    result = await calls_activities.create_escalation(
        calls_activities.CreateEscalationInput(
            key="CALL-ACT-ESC-ACTION-1",
            correlation_id="CALL-ACT-ESC",
            call_id="CALL-ACT-ESC",
            reason="CUSTOMER_REQUESTED_HUMAN",
            context_snapshot={"verification_level": "L1"},
        )
    )
    assert result["reason"] == "CUSTOMER_REQUESTED_HUMAN"


async def test_schedule_callback_activity(db_session_committed):
    seeded = await _seed_full_call(db_session_committed, suffix="8")
    result = await calls_activities.schedule_callback(
        calls_activities.ScheduleCallbackInput(
            key="CALL-ACT-CB-ACTION-1",
            correlation_id="CALL-ACT-CB",
            customer_id=seeded["customer_id"],
            callback_window_start=_NOW,
            callback_window_end=_NOW + timedelta(hours=2),
            reason="CUSTOMER_DRIVING",
        )
    )
    assert result["reason"] == "CUSTOMER_DRIVING"


async def test_create_complaint_activity(db_session_committed):
    seeded = await _seed_full_call(db_session_committed, suffix="9")
    result = await calls_activities.create_complaint(
        calls_activities.CreateComplaintInput(
            key="CALL-ACT-COMP-ACTION-1",
            correlation_id="CALL-ACT-COMP",
            claim_id=seeded["claim_id"],
            source_call_id="CALL-ACT-COMP",
            complaint_category="CLAIM_DELAY",
            customer_statement_summary="test",
            severity="MEDIUM",
            preferred_contact_method="PHONE",
            now=_NOW,
        )
    )
    assert result["severity"] == "MEDIUM"


async def test_finalize_outcome_activity(db_session_committed):
    from src.calls.constants import DispositionCode
    from src.calls.models import CallAttempt

    seeded = await _seed_full_call(db_session_committed, suffix="10")
    async with calls_activities.get_session_factory()() as session, session.begin():
        session.add(
            CallAttempt(
                id="CALL-ACT-10", customer_id=seeded["customer_id"], claim_id=seeded["claim_id"]
            )
        )

    await calls_activities.finalize_outcome(
        calls_activities.FinalizeOutcomeInput(
            call_attempt_id="CALL-ACT-10",
            disposition_code=DispositionCode.SUCCESS_STATUS_DELIVERED.value,
            customer_reached=True,
            right_party=True,
            verified=True,
            verification_level="L1",
            status_delivered="MOTOR_REPAIR_AUTHORIZED",
            resolution="FULLY_RESOLVED_BY_AI",
        )
    )

    async with calls_activities.get_session_factory()() as session:
        row = await session.get(CallAttempt, "CALL-ACT-10")
        assert row.disposition_code == DispositionCode.SUCCESS_STATUS_DELIVERED
        assert row.verified is True
