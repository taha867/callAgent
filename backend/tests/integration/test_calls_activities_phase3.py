"""The remaining Phase 3 calls/activities.py additions not already covered by
test_phase3_transcript_pipeline_e2e.py / test_generate_call_summary.py: record_customer_intent,
record_sentiment_event, record_latency_sample (direct-call shape), get_claim_delay_flag,
count_recent_attempts_activity, record_runtime_failure_event.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from src.audit.models import RuntimeFailureEvent
from src.calls.activities import (
    CountRecentAttemptsInput,
    GetClaimDelayFlagInput,
    RecordCustomerIntentInput,
    RecordLatencySampleInput,
    RecordRuntimeFailureEventInput,
    RecordSentimentEventInput,
    count_recent_attempts_activity,
    get_claim_delay_flag,
    record_customer_intent,
    record_latency_sample,
    record_runtime_failure_event,
    record_sentiment_event,
)
from src.calls.models import CustomerIntent, SentimentEvent
from tests.unit.test_phase3_insert_only import _seed_call_attempt

pytestmark = pytest.mark.integration


async def test_record_customer_intent_activity(db_session_committed):
    attempt = await _seed_call_attempt(db_session_committed, suffix="ACT-INTENT")
    await db_session_committed.commit()

    await record_customer_intent(
        RecordCustomerIntentInput(call_attempt_id=attempt.id, intent="DISSATISFIED", topic="DELAY")
    )

    result = await db_session_committed.execute(
        select(CustomerIntent).where(CustomerIntent.call_attempt_id == attempt.id)
    )
    row = result.scalar_one()
    assert row.intent == "DISSATISFIED"


async def test_record_sentiment_event_activity_direct_call(db_session_committed):
    attempt = await _seed_call_attempt(db_session_committed, suffix="ACT-SENT")
    await db_session_committed.commit()

    await record_sentiment_event(
        RecordSentimentEventInput(
            call_attempt_id=attempt.id,
            turn_index=0,
            sentiment="NEGATIVE",
            signal="SERVICE_FAILURE",
            confidence=0.85,
        )
    )

    result = await db_session_committed.execute(
        select(SentimentEvent).where(SentimentEvent.call_attempt_id == attempt.id)
    )
    row = result.scalar_one()
    assert row.signal == "SERVICE_FAILURE"


async def test_record_latency_sample_activity(db_session_committed):
    attempt = await _seed_call_attempt(db_session_committed, suffix="ACT-LATENCY")
    await db_session_committed.commit()

    await record_latency_sample(
        RecordLatencySampleInput(call_attempt_id=attempt.id, turn_index=0, latency_ms=1234)
    )
    # No exception is the assertion here; row-level correctness is already covered by
    # test_calls_service_phase3.py::test_record_latency_sample.


async def test_get_claim_delay_flag_true(db_session_committed):
    attempt = await _seed_call_attempt(db_session_committed, suffix="ACT-DELAY-TRUE")
    await db_session_committed.commit()
    from src.claims.models import MotorClaim

    claim = await db_session_committed.get(MotorClaim, attempt.claim_id)
    claim.delay_flag = True
    await db_session_committed.commit()

    result = await get_claim_delay_flag(GetClaimDelayFlagInput(claim_id=attempt.claim_id))
    assert result.delay_flag is True


async def test_get_claim_delay_flag_false_by_default(db_session_committed):
    attempt = await _seed_call_attempt(db_session_committed, suffix="ACT-DELAY-FALSE")
    await db_session_committed.commit()

    result = await get_claim_delay_flag(GetClaimDelayFlagInput(claim_id=attempt.claim_id))
    assert result.delay_flag is False


async def test_get_claim_delay_flag_unknown_claim_returns_false(db_session_committed):
    result = await get_claim_delay_flag(GetClaimDelayFlagInput(claim_id="CLM-DOES-NOT-EXIST"))
    assert result.delay_flag is False


async def test_count_recent_attempts_activity(db_session_committed):
    attempt = await _seed_call_attempt(db_session_committed, suffix="ACT-REPEAT")
    await db_session_committed.commit()

    count = await count_recent_attempts_activity(
        CountRecentAttemptsInput(
            customer_id=attempt.customer_id,
            claim_id=attempt.claim_id,
            since=datetime.now() - timedelta(days=1),
        )
    )
    assert count == 1


async def test_record_runtime_failure_event_activity(db_session_committed):
    await record_runtime_failure_event(
        RecordRuntimeFailureEventInput(
            call_id="CALL-STT-FAIL", component="STT", failure_type="STT_TIMEOUT"
        )
    )
    result = await db_session_committed.execute(
        select(RuntimeFailureEvent).where(RuntimeFailureEvent.call_id == "CALL-STT-FAIL")
    )
    row = result.scalar_one()
    assert row.component == "STT"
    assert row.recovery_action == "SAFE_TERMINATION"
