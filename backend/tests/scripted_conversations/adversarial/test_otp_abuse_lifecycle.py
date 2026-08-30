"""AdversarialScenarioId.OTP_ABUSE_LIFECYCLE — spec §10.3.2: resend cooldown, max attempts
-> lockout, expiry. Unit-level against verification/service.py directly (db_session,
rollback-isolated, no Temporal needed) — the workflow-level OTP branch itself
(_run_otp_challenge) is already exercised by the existing Phase 1/2 integration suite; this
phase's job is exercising the abuse-lifecycle edges verification/service.py itself defines.
"""

from datetime import datetime, timedelta

import pytest

from src.verification.adapters.otp_delivery.log_only import LogOtpDeliveryAdapter
from src.verification.config import VerificationConfig
from src.verification.exceptions import (
    OtpExpiredError,
    OtpLockedError,
    OtpResendCooldownError,
)
from src.verification.service import send_otp, verify_otp
from tests.scripted_conversations.conftest import _seed_customer_and_claim


async def _seed_call_session(db, *, suffix: str) -> str:
    from src.calls.models import CallAttempt, CallSession

    seeded = await _seed_customer_and_claim(db, suffix=f"OTP{suffix}")
    attempt_id = f"ATTEMPT-OTP-{suffix}"
    db.add(
        CallAttempt(
            id=attempt_id, customer_id=seeded["customer_id"], claim_id=seeded["claim_id"]
        )
    )
    await db.flush()
    call_session_id = f"SESSION-OTP-{suffix}"
    db.add(CallSession(id=call_session_id, call_attempt_id=attempt_id, state="AUTHENTICATION"))
    await db.flush()
    return call_session_id


async def test_resend_cooldown_blocks_an_immediate_second_send(db_session):
    call_session_id = await _seed_call_session(db_session, suffix="COOLDOWN")
    config = VerificationConfig()
    adapter = LogOtpDeliveryAdapter()
    now = datetime(2026, 9, 1, 10, 0, 0)

    await send_otp(db_session, call_session_id=call_session_id, phone_e164="+971501234567", now=now, config=config, adapter=adapter)

    with pytest.raises(OtpResendCooldownError):
        await send_otp(
            db_session,
            call_session_id=call_session_id,
            phone_e164="+971501234567",
            now=now + timedelta(seconds=1),  # well inside OTP_RESEND_COOLDOWN_SECONDS
            config=config,
            adapter=adapter,
        )


async def test_repeated_wrong_codes_lock_the_challenge(db_session):
    call_session_id = await _seed_call_session(db_session, suffix="LOCKOUT")
    config = VerificationConfig()
    adapter = LogOtpDeliveryAdapter()
    now = datetime(2026, 9, 1, 10, 0, 0)

    challenge = await send_otp(
        db_session, call_session_id=call_session_id, phone_e164="+971501234568", now=now, config=config, adapter=adapter
    )

    last = None
    for _ in range(config.MAX_OTP_ATTEMPTS):
        last = await verify_otp(
            db_session, challenge_id=challenge.id, supplied_code="000000", now=now, config=config
        )

    assert last.status == "LOCKED"

    with pytest.raises(OtpLockedError):
        await verify_otp(
            db_session, challenge_id=challenge.id, supplied_code="000000", now=now, config=config
        )


async def test_expired_challenge_is_rejected(db_session):
    call_session_id = await _seed_call_session(db_session, suffix="EXPIRED")
    config = VerificationConfig()
    adapter = LogOtpDeliveryAdapter()
    now = datetime(2026, 9, 1, 10, 0, 0)

    challenge = await send_otp(
        db_session, call_session_id=call_session_id, phone_e164="+971501234569", now=now, config=config, adapter=adapter
    )

    with pytest.raises(OtpExpiredError):
        await verify_otp(
            db_session,
            challenge_id=challenge.id,
            supplied_code="000000",
            now=now + timedelta(seconds=config.OTP_TTL_SECONDS + 1),
            config=config,
        )
