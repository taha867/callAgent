"""create_call_attempt(), create_call_session(), finalize_outcome() — the plain DB-backed
functions calls/activities.py's activities call. Not imported by calls/workflows.py
directly (see calls/schemas.py's docstring) — only by activities.py, which isn't sandboxed.
"""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.calls.constants import CallState, DispositionCode
from src.calls.models import CallAttempt, CallSession


async def create_call_attempt(
    session: AsyncSession,
    *,
    call_id: str,
    customer_id: str,
    claim_id: str,
    call_job_id: str | None,
    attempt_number: int,
    attempted_at: datetime,
) -> CallAttempt:
    attempt = CallAttempt(
        id=call_id,
        call_job_id=call_job_id,
        customer_id=customer_id,
        claim_id=claim_id,
        attempt_number=attempt_number,
        attempted_at=attempted_at,
    )
    session.add(attempt)
    await session.flush()
    return attempt


async def create_call_session(
    session: AsyncSession, *, call_attempt_id: str, state: CallState
) -> CallSession:
    call_session = CallSession(id=str(uuid.uuid4()), call_attempt_id=call_attempt_id, state=state)
    session.add(call_session)
    await session.flush()
    return call_session


async def update_call_session_language(
    session: AsyncSession, *, call_session_id: str, language: str
) -> None:
    """Called directly by voice/pipeline.py's own DB session (Phase 2) — never through a
    Temporal activity, since this is per-turn conversational-QA state, not deterministic
    call-state the workflow arbitrates. See .claude/specs/phase-2-backend-spec.md §0.7 and
    this module's docstring's "only by activities.py" note, which this function is a
    deliberate, documented exception to."""
    call_session = await session.get(CallSession, call_session_id)
    assert call_session is not None, f"no CallSession row for {call_session_id}"
    call_session.language = language
    await session.flush()


async def finalize_outcome(
    session: AsyncSession,
    *,
    call_attempt_id: str,
    disposition_code: DispositionCode,
    answer_result: str | None = None,
    customer_reached: bool = False,
    right_party: bool | None = None,
    verified: bool = False,
    verification_level: str | None = None,
    status_delivered: str | None = None,
    resolution: str | None = None,
    duration_seconds: int | None = None,
    next_attempt_at: datetime | None = None,
    voicemail_detected: bool = False,
    attempts_remaining: int | None = None,
) -> CallAttempt:
    attempt = await session.get(CallAttempt, call_attempt_id)
    assert attempt is not None, f"finalize_outcome: no CallAttempt row for {call_attempt_id}"

    attempt.disposition_code = disposition_code
    attempt.answer_result = answer_result
    attempt.customer_reached = customer_reached
    attempt.right_party = right_party
    attempt.verified = verified
    attempt.verification_level = verification_level
    attempt.status_delivered = status_delivered
    attempt.resolution = resolution
    attempt.duration_seconds = duration_seconds
    attempt.next_attempt_at = next_attempt_at
    attempt.voicemail_detected = voicemail_detected
    attempt.attempts_remaining = attempts_remaining

    await session.flush()
    return attempt
