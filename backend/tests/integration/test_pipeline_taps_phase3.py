"""voice/pipeline.py's Phase 3 tap changes — transcript persistence, sentiment tagging (+
the DELAY_DISSATISFACTION safety-net signal), the symmetric AI-turn tap, and the latency
tap. Fake frames drive the real tap code, no real Pipecat pipeline/audio — same "drive the
real code, fake the frame" discipline test_runtime_failure_stt_llm_tts.py already
established for the ErrorFrame path.
"""

from unittest.mock import AsyncMock

import pytest
from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection
from sqlalchemy import select

from src.calls.models import CallLatencySample, CallTranscript, SentimentEvent
from src.voice.pipeline import (
    CallPipelineContext,
    _AssistantTranscriptTap,
    _ConversationTapProcessor,
    _LatencyTapProcessor,
)
from tests.unit.test_phase3_insert_only import _seed_call_attempt

pytestmark = pytest.mark.integration


async def _make_ctx(db_session_committed, suffix: str) -> CallPipelineContext:
    attempt = await _seed_call_attempt(db_session_committed, suffix=suffix)
    await db_session_committed.commit()
    return CallPipelineContext(
        call_id=attempt.id,
        customer_id=attempt.customer_id,
        claim_id=attempt.claim_id,
        workflow_handle=AsyncMock(),
    )


async def _transcript_rows(db, call_id: str) -> list[CallTranscript]:
    result = await db.execute(
        select(CallTranscript)
        .where(CallTranscript.call_attempt_id == call_id)
        .order_by(CallTranscript.turn_index)
    )
    return list(result.scalars())


class _FakeSTT:
    """Stands in for get_stt_service() — never constructed for real, avoids a live vendor
    call for whatever _build_prompt_context/claim lookups the tap itself needs."""


async def test_customer_turn_persisted_with_sentiment_and_latency_mark(db_session_committed):
    ctx = await _make_ctx(db_session_committed, "TAP-CUSTOMER")
    llm_context = LLMContext(messages=[{"role": "system", "content": "x"}])
    tap = _ConversationTapProcessor(ctx, llm_context)
    tap._refresh_system_prompt = AsyncMock()  # avoid a real claims/customers DB lookup chain

    frame = TranscriptionFrame(text="What's the status of my claim?", user_id="u1", timestamp="")
    await tap.process_frame(frame, FrameDirection.DOWNSTREAM)

    rows = await _transcript_rows(db_session_committed, ctx.call_id)
    assert len(rows) == 1
    assert rows[0].speaker == "CUSTOMER"
    assert rows[0].redacted_text == "What's the status of my claim?"

    sentiment_result = await db_session_committed.execute(
        select(SentimentEvent).where(SentimentEvent.call_attempt_id == ctx.call_id)
    )
    sentiment_row = sentiment_result.scalar_one()
    assert sentiment_row.turn_index == 0
    assert sentiment_row.sentiment == "NEUTRAL"

    assert ctx.end_of_speech_at is not None
    assert ctx.pending_latency_turn_index == 0
    ctx.workflow_handle.signal.assert_not_called()


async def test_delay_dissatisfaction_signals_workflow_as_safety_net(db_session_committed):
    ctx = await _make_ctx(db_session_committed, "TAP-DELAY")
    llm_context = LLMContext(messages=[{"role": "system", "content": "x"}])
    tap = _ConversationTapProcessor(ctx, llm_context)
    tap._refresh_system_prompt = AsyncMock()

    frame = TranscriptionFrame(
        text="This is ridiculous, I've been waiting two weeks.", user_id="u1", timestamp=""
    )
    await tap.process_frame(frame, FrameDirection.DOWNSTREAM)

    ctx.workflow_handle.signal.assert_awaited_once()
    args, _kwargs = ctx.workflow_handle.signal.call_args
    signal_payload = args[1]
    assert signal_payload.intent == "DISSATISFIED"


async def test_assistant_turn_accumulates_and_persists_on_response_end(db_session_committed):
    ctx = await _make_ctx(db_session_committed, "TAP-AI")
    tap = _AssistantTranscriptTap(ctx)

    await tap.process_frame(LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM)
    await tap.process_frame(LLMTextFrame(text="Your repair "), FrameDirection.DOWNSTREAM)
    await tap.process_frame(LLMTextFrame(text="has been authorised."), FrameDirection.DOWNSTREAM)
    await tap.process_frame(LLMFullResponseEndFrame(), FrameDirection.DOWNSTREAM)

    rows = await _transcript_rows(db_session_committed, ctx.call_id)
    assert len(rows) == 1
    assert rows[0].speaker == "AI"
    assert rows[0].redacted_text == "Your repair has been authorised."
    assert ctx.turn_index == 1


async def test_assistant_turn_empty_response_not_persisted(db_session_committed):
    ctx = await _make_ctx(db_session_committed, "TAP-AI-EMPTY")
    tap = _AssistantTranscriptTap(ctx)

    await tap.process_frame(LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM)
    await tap.process_frame(LLMFullResponseEndFrame(), FrameDirection.DOWNSTREAM)

    rows = await _transcript_rows(db_session_committed, ctx.call_id)
    assert rows == []
    assert ctx.turn_index == 0


async def test_latency_tap_records_sample_on_first_audio_frame_only(db_session_committed):
    ctx = await _make_ctx(db_session_committed, "TAP-LATENCY")
    ctx.end_of_speech_at = __import__("time").monotonic() - 0.5  # 500ms ago
    ctx.pending_latency_turn_index = 2
    tap = _LatencyTapProcessor(ctx)

    audio_frame_1 = TTSAudioRawFrame(audio=b"\x00\x00", sample_rate=16000, num_channels=1)
    audio_frame_2 = TTSAudioRawFrame(audio=b"\x00\x00", sample_rate=16000, num_channels=1)

    await tap.process_frame(audio_frame_1, FrameDirection.DOWNSTREAM)
    # end_of_speech_at is cleared after the first frame — a second audio frame in the same
    # utterance must NOT record a second sample.
    assert ctx.end_of_speech_at is None
    await tap.process_frame(audio_frame_2, FrameDirection.DOWNSTREAM)

    result = await db_session_committed.execute(
        select(CallLatencySample).where(CallLatencySample.call_attempt_id == ctx.call_id)
    )
    samples = result.scalars().all()
    assert len(samples) == 1
    assert samples[0].turn_index == 2
    assert samples[0].latency_ms >= 400  # roughly the ~500ms we set above


async def test_latency_tap_no_sample_without_a_pending_mark(db_session_committed):
    ctx = await _make_ctx(db_session_committed, "TAP-LATENCY-NONE")
    tap = _LatencyTapProcessor(ctx)

    frame = TTSAudioRawFrame(audio=b"\x00\x00", sample_rate=16000, num_channels=1)
    await tap.process_frame(frame, FrameDirection.DOWNSTREAM)

    result = await db_session_committed.execute(
        select(CallLatencySample).where(CallLatencySample.call_attempt_id == ctx.call_id)
    )
    assert result.scalars().all() == []
