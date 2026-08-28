"""calls/service.py's Phase 3 additions — record_transcript_turn/get_redacted_transcript,
record_customer_intent, record_sentiment_event, record_call_summary, record_latency_sample,
count_recent_attempts. Plain DB-backed, no Temporal — same testability class as Phase 1
Batch 6.
"""

from datetime import datetime, timedelta

from src.calls import service as calls_service
from tests.unit.test_phase3_insert_only import _seed_call_attempt


async def test_get_redacted_transcript_returns_turn_index_ordered_rows(db_session):
    attempt = await _seed_call_attempt(db_session, suffix="SVC-ORDER")
    # inserted out of order on purpose
    await calls_service.record_transcript_turn(
        db_session,
        call_attempt_id=attempt.id,
        turn_index=1,
        speaker="AI",
        redacted_text="second",
        language="en",
    )
    await calls_service.record_transcript_turn(
        db_session,
        call_attempt_id=attempt.id,
        turn_index=0,
        speaker="CUSTOMER",
        redacted_text="first",
        language="en",
    )

    turns = await calls_service.get_redacted_transcript(db_session, attempt.id)
    assert [t.turn_index for t in turns] == [0, 1]
    assert [t.redacted_text for t in turns] == ["first", "second"]


async def test_record_customer_intent(db_session):
    attempt = await _seed_call_attempt(db_session, suffix="SVC-INTENT")
    intent = await calls_service.record_customer_intent(
        db_session, call_attempt_id=attempt.id, intent="ASK_QUESTION", topic="ETA"
    )
    assert intent.intent == "ASK_QUESTION"
    assert intent.topic == "ETA"
    assert intent.summary is None


async def test_record_sentiment_event_call_level_row(db_session):
    attempt = await _seed_call_attempt(db_session, suffix="SVC-SENTIMENT")
    event = await calls_service.record_sentiment_event(
        db_session, call_attempt_id=attempt.id, signal="REPEATED_CONTACT", confidence=1.0
    )
    assert event.turn_index is None
    assert event.signal == "REPEATED_CONTACT"


async def test_record_call_summary(db_session):
    attempt = await _seed_call_attempt(db_session, suffix="SVC-SUMMARY")
    summary = await calls_service.record_call_summary(
        db_session, call_attempt_id=attempt.id, summary_text="Status delivered, resolved."
    )
    assert summary.call_attempt_id == attempt.id
    assert summary.summary_text == "Status delivered, resolved."


async def test_record_latency_sample(db_session):
    attempt = await _seed_call_attempt(db_session, suffix="SVC-LATENCY")
    sample = await calls_service.record_latency_sample(
        db_session, call_attempt_id=attempt.id, turn_index=0, latency_ms=920
    )
    assert sample.latency_ms == 920


async def test_count_recent_attempts_windows_correctly(db_session):
    attempt = await _seed_call_attempt(db_session, suffix="SVC-REPEAT")
    now = datetime.now()

    # in-window
    in_window = await calls_service.count_recent_attempts(
        db_session,
        customer_id=attempt.customer_id,
        claim_id=attempt.claim_id,
        since=now - timedelta(days=1),
    )
    assert in_window == 1

    # out-of-window: since is in the future relative to the seeded attempt
    out_of_window = await calls_service.count_recent_attempts(
        db_session,
        customer_id=attempt.customer_id,
        claim_id=attempt.claim_id,
        since=now + timedelta(days=1),
    )
    assert out_of_window == 0

    # different customer/claim entirely — must not be counted
    unrelated = await calls_service.count_recent_attempts(
        db_session,
        customer_id="CUST-UNRELATED",
        claim_id="CLM-UNRELATED",
        since=now - timedelta(days=1),
    )
    assert unrelated == 0
