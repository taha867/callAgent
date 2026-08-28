"""Level 1 (knowledge-factor) and Level 2 (OTP) verification — spec §10, task 5.

Every function takes `now: datetime` as an explicit parameter rather than reading the clock
itself — same discipline campaigns/service.py::check_call_eligibility follows (see
.claude/specs/phase-1-backend-implementation-plan.md's corrections §3): this module stays a
plain, framework-agnostic service, easily unit-tested with a fixed clock, and its caller
(calls/activities.py, which runs inside a Temporal activity — never inside sandboxed
workflow code) decides what "now" means.

MAX_AUTH_ATTEMPTS (Level 1) and MAX_OTP_ATTEMPTS (Level 2) are independent counters against
independent tables (VerificationAttempt vs. OtpChallenge.attempt_count) — spec §10.3.2 is
explicit that OTP controls are independent from Level 1 knowledge-based authentication.
"""

import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.customers.service import get_auth_factor, hash_factor_value
from src.verification.adapters.otp_delivery.base import OtpDeliveryAdapter
from src.verification.config import VerificationConfig
from src.verification.exceptions import (
    AuthFactorNotConfiguredError,
    OtpChallengeNotFoundError,
    OtpExpiredError,
    OtpLockedError,
    OtpResendCooldownError,
    OtpSendLimitExceededError,
)
from src.verification.models import OtpChallenge, VerificationAttempt


async def verify_level1(
    session: AsyncSession,
    *,
    call_session_id: str,
    customer_id: str,
    factor_type: str,
    supplied_value: str,
    now: datetime,
) -> VerificationAttempt:
    """One MAX_AUTH_ATTEMPTS-counted attempt (the caller enforces the attempt limit by
    counting rows returned from a follow-up query — this function only records a single
    comparison outcome, it does not itself decide when to give up)."""
    factor = await get_auth_factor(session, customer_id, factor_type)
    if factor is None:
        raise AuthFactorNotConfiguredError(factor_type)

    outcome = (
        "MATCH" if hash_factor_value(supplied_value) == factor.factor_value_hash else "NO_MATCH"
    )
    attempt = VerificationAttempt(
        call_session_id=call_session_id,
        level="L1",
        factor_type=factor_type,
        outcome=outcome,
        attempted_at=now,
    )
    session.add(attempt)
    await session.flush()
    return attempt


async def count_level1_attempts(session: AsyncSession, call_session_id: str) -> int:
    result = await session.execute(
        select(VerificationAttempt).where(
            VerificationAttempt.call_session_id == call_session_id,
            VerificationAttempt.level == "L1",
        )
    )
    return len(result.scalars().all())


async def send_otp(
    session: AsyncSession,
    *,
    call_session_id: str,
    phone_e164: str,
    now: datetime,
    config: VerificationConfig,
    adapter: OtpDeliveryAdapter,
) -> OtpChallenge:
    existing = await _get_challenge_for_session(session, call_session_id)

    if existing is not None:
        if existing.sent_count >= config.MAX_OTP_SENDS_PER_SESSION:
            raise OtpSendLimitExceededError(call_session_id)
        cooldown_until = existing.created_at + timedelta(seconds=config.OTP_RESEND_COOLDOWN_SECONDS)
        if now < cooldown_until:
            raise OtpResendCooldownError(call_session_id)

    code = f"{secrets.randbelow(10**6):06d}"
    await adapter.send(phone_e164=phone_e164, code=code)

    if existing is None:
        challenge = OtpChallenge(
            call_session_id=call_session_id,
            code_hash=hash_factor_value(code),
            sent_count=1,
            attempt_count=0,
            status="SENT",
            expires_at=now + timedelta(seconds=config.OTP_TTL_SECONDS),
            created_at=now,
        )
        session.add(challenge)
    else:
        existing.code_hash = hash_factor_value(code)
        existing.sent_count += 1
        existing.attempt_count = 0
        existing.status = "SENT"
        existing.expires_at = now + timedelta(seconds=config.OTP_TTL_SECONDS)
        existing.created_at = now
        challenge = existing

    await session.flush()
    return challenge


async def verify_otp(
    session: AsyncSession,
    *,
    challenge_id: str,
    supplied_code: str,
    now: datetime,
    config: VerificationConfig,
) -> OtpChallenge:
    challenge = await session.get(OtpChallenge, challenge_id)
    if challenge is None:
        raise OtpChallengeNotFoundError(challenge_id)

    if challenge.status == "LOCKED" and challenge.locked_until and now < challenge.locked_until:
        raise OtpLockedError(challenge_id)

    if now >= challenge.expires_at:
        challenge.status = "EXPIRED"
        await session.flush()
        raise OtpExpiredError(challenge_id)

    if hash_factor_value(supplied_code) == challenge.code_hash:
        challenge.status = "VERIFIED"
        await session.flush()
        return challenge

    challenge.attempt_count += 1
    if challenge.attempt_count >= config.MAX_OTP_ATTEMPTS:
        challenge.status = "LOCKED"
        challenge.locked_until = now + timedelta(minutes=config.OTP_LOCKOUT_MINUTES)
    await session.flush()
    return challenge


async def _get_challenge_for_session(
    session: AsyncSession, call_session_id: str
) -> OtpChallenge | None:
    result = await session.execute(
        select(OtpChallenge)
        .where(OtpChallenge.call_session_id == call_session_id)
        .order_by(OtpChallenge.created_at.desc())
    )
    return result.scalars().first()
