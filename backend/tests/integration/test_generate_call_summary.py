"""calls/activities.py::generate_call_summary — built from CallAttempt + CustomerIntent
only (never CallTranscript, spec §0.7), the final-sentiment row derived deterministically
from the last per-turn SentimentEvent (never LLM-derived), and a forced adapter failure
must surface from the activity itself rather than being silently swallowed (the workflow,
Batch 8, is what decides best-effort semantics at the call site).
"""

import pytest
from sqlalchemy import select

from src.calls import service as calls_service
from src.calls.activities import GenerateCallSummaryInput, generate_call_summary
from src.calls.models import CallSummary, SentimentEvent
from tests.unit.test_phase3_insert_only import _seed_call_attempt

pytestmark = pytest.mark.integration


class _FakeAdapter:
    def __init__(self, response=None, *, raises: bool = False):
        self._response = response or {"summary_text": "Status delivered, call resolved."}
        self._raises = raises

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        if self._raises:
            raise RuntimeError("simulated LLM failure")
        return self._response


async def test_generate_call_summary_writes_summary_and_final_sentiment(
    db_session_committed, monkeypatch
):
    attempt = await _seed_call_attempt(db_session_committed, suffix="SUMMARY-OK")
    await calls_service.record_customer_intent(
        db_session_committed, call_attempt_id=attempt.id, intent="ASK_QUESTION", topic="ETA"
    )
    await calls_service.record_sentiment_event(
        db_session_committed, call_attempt_id=attempt.id, turn_index=0, sentiment="NEUTRAL"
    )
    await calls_service.record_sentiment_event(
        db_session_committed, call_attempt_id=attempt.id, turn_index=1, sentiment="POSITIVE"
    )
    await db_session_committed.commit()

    monkeypatch.setattr("src.voice.adapters.llm.get_completion_adapter", lambda: _FakeAdapter())

    await generate_call_summary(GenerateCallSummaryInput(call_attempt_id=attempt.id))

    summary_result = await db_session_committed.execute(
        select(CallSummary).where(CallSummary.call_attempt_id == attempt.id)
    )
    summary = summary_result.scalar_one()
    assert summary.summary_text == "Status delivered, call resolved."

    sentiment_result = await db_session_committed.execute(
        select(SentimentEvent).where(
            SentimentEvent.call_attempt_id == attempt.id, SentimentEvent.turn_index.is_(None)
        )
    )
    final_row = sentiment_result.scalar_one()
    # last per-turn row (turn_index=1) was POSITIVE — final sentiment must reflect THAT,
    # not be LLM-derived.
    assert final_row.sentiment == "POSITIVE"


async def test_generate_call_summary_redacts_llm_output_defensively(
    db_session_committed, monkeypatch
):
    attempt = await _seed_call_attempt(db_session_committed, suffix="SUMMARY-REDACT")
    await db_session_committed.commit()

    monkeypatch.setattr(
        "src.voice.adapters.llm.get_completion_adapter",
        lambda: _FakeAdapter({"summary_text": "Contact at customer@example.com for follow-up."}),
    )

    await generate_call_summary(GenerateCallSummaryInput(call_attempt_id=attempt.id))

    summary_result = await db_session_committed.execute(
        select(CallSummary).where(CallSummary.call_attempt_id == attempt.id)
    )
    summary = summary_result.scalar_one()
    assert "customer@example.com" not in summary.summary_text
    assert "[EMAIL_ADDRESS_REDACTED]" in summary.summary_text


async def test_generate_call_summary_failure_surfaces_not_swallowed(
    db_session_committed, monkeypatch
):
    attempt = await _seed_call_attempt(db_session_committed, suffix="SUMMARY-FAIL")
    await db_session_committed.commit()

    monkeypatch.setattr(
        "src.voice.adapters.llm.get_completion_adapter",
        lambda: _FakeAdapter(raises=True),
    )

    with pytest.raises(RuntimeError, match="simulated LLM failure"):
        await generate_call_summary(GenerateCallSummaryInput(call_attempt_id=attempt.id))

    summary_result = await db_session_committed.execute(
        select(CallSummary).where(CallSummary.call_attempt_id == attempt.id)
    )
    assert summary_result.scalar_one_or_none() is None
