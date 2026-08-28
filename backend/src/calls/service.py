"""create_call_attempt(), create_call_session(), finalize_outcome() — the plain DB-backed
functions calls/activities.py's activities call. Not imported by calls/workflows.py
directly (see calls/schemas.py's docstring) — only by activities.py, which isn't sandboxed.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.calls.constants import CallState, DispositionCode
from src.calls.models import (
    CallAttempt,
    CallLatencySample,
    CallSession,
    CallSummary,
    CallTranscript,
    CustomerIntent,
    SentimentEvent,
)


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


# --- Phase 3: transcript, summary, intent, sentiment, latency ---------------------------
# Every function below is a plain insert/query, no idempotency wrapper — record_transcript_
# turn's PiiRedactionEvent side-effect (privacy/service.py::record_redaction_events) is the
# idempotent write; a CallTranscript row itself is protected only by the unique constraint
# on (call_attempt_id, turn_index, speaker) (calls/models.py), per
# .claude/plans/phase-3-backend-implementation-plan.md Correction 2.


async def record_transcript_turn(
    session: AsyncSession,
    *,
    call_attempt_id: str,
    turn_index: int,
    speaker: str,
    redacted_text: str,
    language: str,
) -> CallTranscript:
    turn = CallTranscript(
        call_attempt_id=call_attempt_id,
        turn_index=turn_index,
        speaker=speaker,
        redacted_text=redacted_text,
        language=language,
    )
    session.add(turn)
    await session.flush()
    return turn


async def get_redacted_transcript(
    session: AsyncSession, call_attempt_id: str
) -> list[CallTranscript]:
    """The literal function CLAUDE.md §1's own worked example names
    (calls/router.py's get_call_transcript route). Ordered by turn_index — the one shared,
    monotonically-increasing counter across both CUSTOMER and AI-authored rows
    (calls/models.py::CallTranscript's docstring)."""
    result = await session.execute(
        select(CallTranscript)
        .where(CallTranscript.call_attempt_id == call_attempt_id)
        .order_by(CallTranscript.turn_index)
    )
    return list(result.scalars())


async def get_call_summary(session: AsyncSession, call_attempt_id: str) -> CallSummary | None:
    result = await session.execute(
        select(CallSummary).where(CallSummary.call_attempt_id == call_attempt_id)
    )
    return result.scalar_one_or_none()


async def get_customer_intents(session: AsyncSession, call_attempt_id: str) -> list[CustomerIntent]:
    result = await session.execute(
        select(CustomerIntent)
        .where(CustomerIntent.call_attempt_id == call_attempt_id)
        .order_by(CustomerIntent.created_at)
    )
    return list(result.scalars())


async def get_sentiment_events(session: AsyncSession, call_attempt_id: str) -> list[SentimentEvent]:
    result = await session.execute(
        select(SentimentEvent)
        .where(SentimentEvent.call_attempt_id == call_attempt_id)
        .order_by(SentimentEvent.created_at)
    )
    return list(result.scalars())


async def get_last_turn_sentiment(session: AsyncSession, call_attempt_id: str) -> str | None:
    """The most recent PER-TURN sentiment reading (turn_index IS NOT NULL) — used by
    calls/activities.py::generate_call_summary to write the call-level "final sentiment"
    row deterministically, never LLM-derived (see that function's own docstring)."""
    result = await session.execute(
        select(SentimentEvent.sentiment)
        .where(
            SentimentEvent.call_attempt_id == call_attempt_id,
            SentimentEvent.turn_index.is_not(None),
        )
        .order_by(SentimentEvent.turn_index.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def record_customer_intent(
    session: AsyncSession,
    *,
    call_attempt_id: str,
    intent: str,
    topic: str | None = None,
    summary: str | None = None,
) -> CustomerIntent:
    record = CustomerIntent(
        call_attempt_id=call_attempt_id, intent=intent, topic=topic, summary=summary
    )
    session.add(record)
    await session.flush()
    return record


async def record_sentiment_event(
    session: AsyncSession,
    *,
    call_attempt_id: str,
    turn_index: int | None = None,
    sentiment: str | None = None,
    signal: str | None = None,
    confidence: float = 1.0,
) -> SentimentEvent:
    event = SentimentEvent(
        call_attempt_id=call_attempt_id,
        turn_index=turn_index,
        sentiment=sentiment,
        signal=signal,
        confidence=confidence,
    )
    session.add(event)
    await session.flush()
    return event


async def record_call_summary(
    session: AsyncSession, *, call_attempt_id: str, summary_text: str
) -> CallSummary:
    summary = CallSummary(call_attempt_id=call_attempt_id, summary_text=summary_text)
    session.add(summary)
    await session.flush()
    return summary


async def record_latency_sample(
    session: AsyncSession, *, call_attempt_id: str, turn_index: int, latency_ms: int
) -> CallLatencySample:
    sample = CallLatencySample(
        call_attempt_id=call_attempt_id, turn_index=turn_index, latency_ms=latency_ms
    )
    session.add(sample)
    await session.flush()
    return sample


async def count_recent_attempts(
    session: AsyncSession, *, customer_id: str, claim_id: str, since: datetime
) -> int:
    """Deterministic REPEATED_CONTACT check (spec §18/§31) — a DB count, never an LLM
    inference (CLAUDE.md §4's "never let LLM/customer assumption substitute for the engine
    checking real state")."""
    result = await session.execute(
        select(func.count(CallAttempt.id)).where(
            CallAttempt.customer_id == customer_id,
            CallAttempt.claim_id == claim_id,
            CallAttempt.attempted_at >= since,
        )
    )
    return result.scalar_one()
