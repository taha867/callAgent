"""verification/service.py — Level 1 knowledge-factor verification and the Level 2 OTP
state machine (spec §10, §10.3.2). Testable with the existing db_session fixture, no
temporal_env needed — verification/service.py is a plain DB-backed service.
"""

from datetime import datetime, timedelta

import pytest

from src.customers.service import hash_factor_value
from src.verification.adapters.otp_delivery.log_only import (
    LogOtpDeliveryAdapter,
    get_last_sent_code_for_testing,
)
from src.verification.config import VerificationConfig
from src.verification.exceptions import (
    AuthFactorNotConfiguredError,
    OtpExpiredError,
    OtpLockedError,
    OtpResendCooldownError,
    OtpSendLimitExceededError,
)
from src.verification.models import OtpChallenge
from src.verification.service import (
    count_level1_attempts,
    send_otp,
    verify_level1,
    verify_otp,
)

_NOW = datetime(2026, 8, 27, 12, 0, 0)


def _config(**overrides) -> VerificationConfig:
    return VerificationConfig(_env_file=None, **overrides)


async def _seed_call_session(
    db_session, *, suffix: str, factor_value: str = "1990"
) -> tuple[str, str]:
    """Seeds Customer -> MotorPolicy -> MotorClaim -> CallAttempt -> CallSession plus one
    CustomerAuthFactor. Returns (customer_id, call_session_id)."""
    from src.calls.constants import CallState
    from src.calls.models import CallAttempt, CallSession
    from src.claims.constants import ClaimStage
    from src.claims.models import MotorClaim, MotorPolicy
    from src.customers.models import Customer, CustomerAuthFactor

    customer_id = f"CUST-VER-{suffix}"
    db_session.add(Customer(id=customer_id, full_name="x", phone_e164=f"+9715{suffix}"))
    await db_session.flush()
    db_session.add(
        CustomerAuthFactor(
            id=f"FACTOR-{suffix}",
            customer_id=customer_id,
            factor_type="BIRTH_MONTH_YEAR",
            factor_value_hash=hash_factor_value(factor_value),
        )
    )
    db_session.add(
        MotorPolicy(
            id=f"POL-VER-{suffix}",
            customer_id=customer_id,
            policy_number="P1",
            vehicle_plate="X",
            vehicle_make_model="Y",
        )
    )
    await db_session.flush()
    db_session.add(
        MotorClaim(
            id=f"CLM-VER-{suffix}",
            policy_id=f"POL-VER-{suffix}",
            customer_id=customer_id,
            claim_stage=ClaimStage.CLAIM_REGISTERED,
            language="en",
        )
    )
    await db_session.flush()
    db_session.add(
        CallAttempt(
            id=f"CALL-VER-{suffix}",
            customer_id=customer_id,
            claim_id=f"CLM-VER-{suffix}",
        )
    )
    await db_session.flush()
    call_session_id = f"SESS-VER-{suffix}"
    db_session.add(
        CallSession(
            id=call_session_id,
            call_attempt_id=f"CALL-VER-{suffix}",
            state=CallState.AUTHENTICATION,
        )
    )
    await db_session.flush()
    return customer_id, call_session_id


async def test_verify_level1_match(db_session):
    customer_id, call_session_id = await _seed_call_session(db_session, suffix="L1MATCH")
    attempt = await verify_level1(
        db_session,
        call_session_id=call_session_id,
        customer_id=customer_id,
        factor_type="BIRTH_MONTH_YEAR",
        supplied_value="1990",
        now=_NOW,
    )
    assert attempt.outcome == "MATCH"


async def test_verify_level1_no_match(db_session):
    customer_id, call_session_id = await _seed_call_session(db_session, suffix="L1NOMATCH")
    attempt = await verify_level1(
        db_session,
        call_session_id=call_session_id,
        customer_id=customer_id,
        factor_type="BIRTH_MONTH_YEAR",
        supplied_value="wrong",
        now=_NOW,
    )
    assert attempt.outcome == "NO_MATCH"


async def test_verify_level1_missing_factor_raises(db_session):
    customer_id, call_session_id = await _seed_call_session(db_session, suffix="L1MISSING")
    with pytest.raises(AuthFactorNotConfiguredError):
        await verify_level1(
            db_session,
            call_session_id=call_session_id,
            customer_id=customer_id,
            factor_type="PLATE_LAST4",  # never configured for this customer
            supplied_value="1234",
            now=_NOW,
        )


async def test_count_level1_attempts_reflects_max_auth_attempts_enforcement(db_session):
    customer_id, call_session_id = await _seed_call_session(db_session, suffix="L1COUNT")
    for _ in range(2):
        await verify_level1(
            db_session,
            call_session_id=call_session_id,
            customer_id=customer_id,
            factor_type="BIRTH_MONTH_YEAR",
            supplied_value="wrong",
            now=_NOW,
        )
    assert await count_level1_attempts(db_session, call_session_id) == 2


async def test_send_otp_then_verify_correct_code(db_session):
    _, call_session_id = await _seed_call_session(db_session, suffix="OTP1")
    config = _config()
    adapter = LogOtpDeliveryAdapter()
    challenge = await send_otp(
        db_session,
        call_session_id=call_session_id,
        phone_e164="+971500000001",
        now=_NOW,
        config=config,
        adapter=adapter,
    )
    code = get_last_sent_code_for_testing("+971500000001")
    assert code is not None
    assert len(code) == 6

    verified = await verify_otp(
        db_session, challenge_id=challenge.id, supplied_code=code, now=_NOW, config=config
    )
    assert verified.status == "VERIFIED"


async def test_verify_otp_wrong_code_increments_attempt_count(db_session):
    _, call_session_id = await _seed_call_session(db_session, suffix="OTP2")
    config = _config()
    adapter = LogOtpDeliveryAdapter()
    challenge = await send_otp(
        db_session,
        call_session_id=call_session_id,
        phone_e164="+971500000002",
        now=_NOW,
        config=config,
        adapter=adapter,
    )
    result = await verify_otp(
        db_session, challenge_id=challenge.id, supplied_code="000000", now=_NOW, config=config
    )
    assert result.status == "SENT"
    assert result.attempt_count == 1


async def test_verify_otp_locks_after_max_attempts(db_session):
    _, call_session_id = await _seed_call_session(db_session, suffix="OTP3")
    config = _config(MAX_OTP_ATTEMPTS=3)
    adapter = LogOtpDeliveryAdapter()
    challenge = await send_otp(
        db_session,
        call_session_id=call_session_id,
        phone_e164="+971500000003",
        now=_NOW,
        config=config,
        adapter=adapter,
    )
    for _ in range(3):
        result = await verify_otp(
            db_session, challenge_id=challenge.id, supplied_code="000000", now=_NOW, config=config
        )
    assert result.status == "LOCKED"
    assert result.locked_until == _NOW + timedelta(minutes=config.OTP_LOCKOUT_MINUTES)


async def test_verify_otp_locked_raises_before_lockout_expires(db_session):
    _, call_session_id = await _seed_call_session(db_session, suffix="OTP4")
    config = _config(MAX_OTP_ATTEMPTS=1)
    adapter = LogOtpDeliveryAdapter()
    challenge = await send_otp(
        db_session,
        call_session_id=call_session_id,
        phone_e164="+971500000004",
        now=_NOW,
        config=config,
        adapter=adapter,
    )
    await verify_otp(
        db_session, challenge_id=challenge.id, supplied_code="000000", now=_NOW, config=config
    )  # locks immediately (MAX_OTP_ATTEMPTS=1)

    with pytest.raises(OtpLockedError):
        await verify_otp(
            db_session,
            challenge_id=challenge.id,
            supplied_code="000000",
            now=_NOW + timedelta(seconds=1),
            config=config,
        )


async def test_verify_otp_expired_raises(db_session):
    _, call_session_id = await _seed_call_session(db_session, suffix="OTP5")
    config = _config(OTP_TTL_SECONDS=180)
    adapter = LogOtpDeliveryAdapter()
    challenge = await send_otp(
        db_session,
        call_session_id=call_session_id,
        phone_e164="+971500000005",
        now=_NOW,
        config=config,
        adapter=adapter,
    )
    code = get_last_sent_code_for_testing("+971500000005")

    with pytest.raises(OtpExpiredError):
        await verify_otp(
            db_session,
            challenge_id=challenge.id,
            supplied_code=code,
            now=_NOW + timedelta(seconds=181),
            config=config,
        )


async def test_send_otp_resend_cooldown_raises(db_session):
    _, call_session_id = await _seed_call_session(db_session, suffix="OTP6")
    config = _config(OTP_RESEND_COOLDOWN_SECONDS=30, MAX_OTP_SENDS_PER_SESSION=2)
    adapter = LogOtpDeliveryAdapter()
    await send_otp(
        db_session,
        call_session_id=call_session_id,
        phone_e164="+971500000006",
        now=_NOW,
        config=config,
        adapter=adapter,
    )
    with pytest.raises(OtpResendCooldownError):
        await send_otp(
            db_session,
            call_session_id=call_session_id,
            phone_e164="+971500000006",
            now=_NOW + timedelta(seconds=10),
            config=config,
            adapter=adapter,
        )


async def test_send_otp_respects_cooldown_then_succeeds(db_session):
    _, call_session_id = await _seed_call_session(db_session, suffix="OTP7")
    config = _config(OTP_RESEND_COOLDOWN_SECONDS=30, MAX_OTP_SENDS_PER_SESSION=2)
    adapter = LogOtpDeliveryAdapter()
    await send_otp(
        db_session,
        call_session_id=call_session_id,
        phone_e164="+971500000007",
        now=_NOW,
        config=config,
        adapter=adapter,
    )
    second = await send_otp(
        db_session,
        call_session_id=call_session_id,
        phone_e164="+971500000007",
        now=_NOW + timedelta(seconds=31),
        config=config,
        adapter=adapter,
    )
    assert second.sent_count == 2


async def test_send_otp_sends_limit_exceeded_raises(db_session):
    _, call_session_id = await _seed_call_session(db_session, suffix="OTP8")
    config = _config(OTP_RESEND_COOLDOWN_SECONDS=0, MAX_OTP_SENDS_PER_SESSION=1)
    adapter = LogOtpDeliveryAdapter()
    await send_otp(
        db_session,
        call_session_id=call_session_id,
        phone_e164="+971500000008",
        now=_NOW,
        config=config,
        adapter=adapter,
    )
    with pytest.raises(OtpSendLimitExceededError):
        await send_otp(
            db_session,
            call_session_id=call_session_id,
            phone_e164="+971500000008",
            now=_NOW + timedelta(seconds=1),
            config=config,
            adapter=adapter,
        )


async def test_otp_code_never_persisted_in_plaintext(db_session):
    """spec §36 rule 18 — the stored row must never equal the plaintext code."""
    _, call_session_id = await _seed_call_session(db_session, suffix="OTP9")
    config = _config()
    adapter = LogOtpDeliveryAdapter()
    challenge = await send_otp(
        db_session,
        call_session_id=call_session_id,
        phone_e164="+971500000009",
        now=_NOW,
        config=config,
        adapter=adapter,
    )
    code = get_last_sent_code_for_testing("+971500000009")
    stored = await db_session.get(OtpChallenge, challenge.id)
    assert stored.code_hash != code
    assert code not in stored.code_hash
