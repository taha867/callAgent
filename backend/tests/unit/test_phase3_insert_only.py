"""Mirrors tests/unit/test_runtime_failure_and_complaint_sla_insert_only.py's pattern for
Phase 3's six new insert-only tables — pii_redaction_event (src/privacy/models.py) and
call_transcript/call_summary/customer_intent/sentiment_event/call_latency_sample
(src/calls/models.py) — all guarded by the shared src.insert_only mechanism. Written before
the grant-extension migration per
.claude/plans/phase-3-backend-implementation-plan.md Batch 1.
"""

from datetime import datetime

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from src.calls.models import (
    CallAttempt,
    CallLatencySample,
    CallSummary,
    CallTranscript,
    CustomerIntent,
    SentimentEvent,
)
from src.exceptions import InsertOnlyTableViolationError
from src.privacy.constants import PiiCategory
from src.privacy.models import PiiRedactionEvent


async def _seed_call_attempt(db_session, *, suffix: str) -> CallAttempt:
    from src.claims.constants import ClaimStage
    from src.claims.models import MotorClaim, MotorPolicy
    from src.customers.models import Customer

    db_session.add(Customer(id=f"CUST-P3-{suffix}", full_name="x", phone_e164="+1"))
    await db_session.flush()
    db_session.add(
        MotorPolicy(
            id=f"POL-P3-{suffix}",
            customer_id=f"CUST-P3-{suffix}",
            policy_number="P1",
            vehicle_plate="X",
            vehicle_make_model="Y",
        )
    )
    await db_session.flush()
    db_session.add(
        MotorClaim(
            id=f"CLM-P3-{suffix}",
            policy_id=f"POL-P3-{suffix}",
            customer_id=f"CUST-P3-{suffix}",
            claim_stage=ClaimStage.CLAIM_REGISTERED,
            language="en",
        )
    )
    await db_session.flush()
    attempt = CallAttempt(
        id=f"CALL-P3-{suffix}",
        customer_id=f"CUST-P3-{suffix}",
        claim_id=f"CLM-P3-{suffix}",
        attempted_at=datetime.now(),
    )
    db_session.add(attempt)
    await db_session.flush()
    return attempt


# --- pii_redaction_event ---------------------------------------------------------------


async def test_pii_redaction_event_instance_update_raises(db_session):
    event = PiiRedactionEvent(
        call_id="CALL-PII-1", turn_index=0, category=PiiCategory.EMIRATES_ID, detector="REGEX"
    )
    db_session.add(event)
    await db_session.flush()

    event.detector = "TAMPERED"
    with pytest.raises(InsertOnlyTableViolationError):
        await db_session.flush()


async def test_pii_redaction_event_instance_delete_raises(db_session):
    event = PiiRedactionEvent(
        call_id="CALL-PII-2", turn_index=0, category=PiiCategory.IBAN, detector="CHECKSUM"
    )
    db_session.add(event)
    await db_session.flush()

    await db_session.delete(event)
    with pytest.raises(InsertOnlyTableViolationError):
        await db_session.flush()


async def test_pii_redaction_event_bulk_update_raises(db_session):
    db_session.add(
        PiiRedactionEvent(
            call_id="CALL-PII-3",
            turn_index=0,
            category=PiiCategory.CARD_NUMBER,
            detector="CHECKSUM",
        )
    )
    await db_session.flush()

    with pytest.raises(InsertOnlyTableViolationError):
        await db_session.execute(update(PiiRedactionEvent).values(detector="BULK_TAMPERED"))


# --- call_transcript ---------------------------------------------------------------------


async def test_call_transcript_instance_update_raises(db_session):
    attempt = await _seed_call_attempt(db_session, suffix="CT-UPD")
    turn = CallTranscript(
        call_attempt_id=attempt.id,
        turn_index=0,
        speaker="CUSTOMER",
        redacted_text="hello",
        language="en",
    )
    db_session.add(turn)
    await db_session.flush()

    turn.redacted_text = "TAMPERED"
    with pytest.raises(InsertOnlyTableViolationError):
        await db_session.flush()


async def test_call_transcript_instance_delete_raises(db_session):
    attempt = await _seed_call_attempt(db_session, suffix="CT-DEL")
    turn = CallTranscript(
        call_attempt_id=attempt.id,
        turn_index=0,
        speaker="CUSTOMER",
        redacted_text="hello",
        language="en",
    )
    db_session.add(turn)
    await db_session.flush()

    await db_session.delete(turn)
    with pytest.raises(InsertOnlyTableViolationError):
        await db_session.flush()


async def test_call_transcript_duplicate_turn_rejected(db_session):
    """Correction 2 — the (call_attempt_id, turn_index, speaker) unique constraint rejects
    a duplicated direct-call write."""
    attempt = await _seed_call_attempt(db_session, suffix="CT-DUP")
    db_session.add(
        CallTranscript(
            call_attempt_id=attempt.id,
            turn_index=0,
            speaker="CUSTOMER",
            redacted_text="first",
            language="en",
        )
    )
    await db_session.flush()

    db_session.add(
        CallTranscript(
            call_attempt_id=attempt.id,
            turn_index=0,
            speaker="CUSTOMER",
            redacted_text="duplicate",
            language="en",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_call_transcript_same_turn_different_speaker_allowed(db_session):
    """turn_index is a SHARED counter across speakers (module docstring) — the unique
    constraint is 3-column, not 2, so the same turn_index for a different speaker is a
    distinct, allowed row (in practice turn_index still won't collide across speakers since
    it's monotonically incremented once per persisted turn, but the constraint itself must
    not accidentally forbid this)."""
    attempt = await _seed_call_attempt(db_session, suffix="CT-MULTI")
    db_session.add(
        CallTranscript(
            call_attempt_id=attempt.id,
            turn_index=0,
            speaker="CUSTOMER",
            redacted_text="hi",
            language="en",
        )
    )
    await db_session.flush()
    db_session.add(
        CallTranscript(
            call_attempt_id=attempt.id,
            turn_index=1,
            speaker="AI",
            redacted_text="hello, how can I help",
            language="en",
        )
    )
    await db_session.flush()  # no raise


# --- call_summary ------------------------------------------------------------------------


async def test_call_summary_instance_update_raises(db_session):
    attempt = await _seed_call_attempt(db_session, suffix="CS-UPD")
    summary = CallSummary(call_attempt_id=attempt.id, summary_text="all good")
    db_session.add(summary)
    await db_session.flush()

    summary.summary_text = "TAMPERED"
    with pytest.raises(InsertOnlyTableViolationError):
        await db_session.flush()


async def test_call_summary_duplicate_rejected(db_session):
    attempt = await _seed_call_attempt(db_session, suffix="CS-DUP")
    db_session.add(CallSummary(call_attempt_id=attempt.id, summary_text="first"))
    await db_session.flush()

    db_session.add(CallSummary(call_attempt_id=attempt.id, summary_text="second"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


# --- customer_intent ---------------------------------------------------------------------


async def test_customer_intent_instance_delete_raises(db_session):
    attempt = await _seed_call_attempt(db_session, suffix="CI-DEL")
    intent = CustomerIntent(call_attempt_id=attempt.id, intent="ASK_QUESTION")
    db_session.add(intent)
    await db_session.flush()

    await db_session.delete(intent)
    with pytest.raises(InsertOnlyTableViolationError):
        await db_session.flush()


# --- sentiment_event ---------------------------------------------------------------------


async def test_sentiment_event_bulk_update_raises(db_session):
    attempt = await _seed_call_attempt(db_session, suffix="SE-BULK")
    db_session.add(SentimentEvent(call_attempt_id=attempt.id, turn_index=0, sentiment="NEGATIVE"))
    await db_session.flush()

    with pytest.raises(InsertOnlyTableViolationError):
        await db_session.execute(update(SentimentEvent).values(sentiment="BULK_TAMPERED"))


# --- call_latency_sample -------------------------------------------------------------------


async def test_call_latency_sample_instance_update_raises(db_session):
    attempt = await _seed_call_attempt(db_session, suffix="CL-UPD")
    sample = CallLatencySample(call_attempt_id=attempt.id, turn_index=0, latency_ms=850)
    db_session.add(sample)
    await db_session.flush()

    sample.latency_ms = 1
    with pytest.raises(InsertOnlyTableViolationError):
        await db_session.flush()


# --- role-level enforcement (requires a two-role DB, per existing precedent) --------------


@pytest.mark.integration
@pytest.mark.requires_two_role_db
async def test_app_role_cannot_mutate_pii_redaction_event(db_session_committed, admin_engine):
    async with admin_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO pii_redaction_event (id, call_id, turn_index, category, detector) "
                "VALUES ('PRE-ROLE-TEST', 'CALL-ROLE', 0, 'EMIRATES_ID', 'REGEX')"
            )
        )

    for stmt in (
        "UPDATE pii_redaction_event SET detector='X' WHERE id='PRE-ROLE-TEST'",
        "DELETE FROM pii_redaction_event WHERE id='PRE-ROLE-TEST'",
        "TRUNCATE pii_redaction_event",
    ):
        with pytest.raises((ProgrammingError, DBAPIError)) as exc_info:
            await db_session_committed.execute(text(stmt))
            await db_session_committed.commit()
        assert "permission denied" in str(exc_info.value).lower()
        await db_session_committed.rollback()

    async with admin_engine.begin() as conn:
        await conn.execute(text("TRUNCATE pii_redaction_event"))


@pytest.mark.integration
@pytest.mark.requires_two_role_db
async def test_app_role_cannot_mutate_call_transcript(db_session_committed, admin_engine):
    attempt = await _seed_call_attempt(db_session_committed, suffix="ROLE-CT")
    await db_session_committed.commit()

    async with admin_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO call_transcript "
                "(id, call_attempt_id, turn_index, speaker, redacted_text, language) "
                f"VALUES ('CTR-ROLE-TEST', '{attempt.id}', 0, 'CUSTOMER', 'hi', 'en')"
            )
        )

    for stmt in (
        "UPDATE call_transcript SET redacted_text='X' WHERE id='CTR-ROLE-TEST'",
        "DELETE FROM call_transcript WHERE id='CTR-ROLE-TEST'",
        "TRUNCATE call_transcript",
    ):
        with pytest.raises((ProgrammingError, DBAPIError)) as exc_info:
            await db_session_committed.execute(text(stmt))
            await db_session_committed.commit()
        assert "permission denied" in str(exc_info.value).lower()
        await db_session_committed.rollback()

    async with admin_engine.begin() as conn:
        await conn.execute(text("TRUNCATE call_transcript CASCADE"))
