"""spec §5.3 — voice/pipeline.py's _ConversationTapProcessor now records a
RuntimeFailureEvent for a real STT/LLM/TTS service ErrorFrame, extending the
component vocabulary beyond deliver_status's existing "BACKEND"-only coverage. Fault
injection: a fabricated ErrorFrame stands in for a real Pipecat service failure — no real
audio/network needed, same "drive the real code, fake the frame" discipline
test_phase2_pipeline_signal_bridge.py already established for the signal side.
"""

from unittest.mock import MagicMock

import pytest
from pipecat.frames.frames import ErrorFrame, TranscriptionFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.llm_service import LLMService
from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService
from sqlalchemy import select

from src.audit.models import RuntimeFailureEvent
from src.voice.pipeline import CallPipelineContext, _ConversationTapProcessor

pytestmark = pytest.mark.integration


def _make_tap() -> _ConversationTapProcessor:
    ctx = CallPipelineContext(
        call_id="CALL-RTF-TEST",
        customer_id="CUST-X",
        claim_id="CLM-X",
        workflow_handle=MagicMock(),
    )
    llm_context = LLMContext(messages=[{"role": "system", "content": "x"}])
    return _ConversationTapProcessor(ctx, llm_context)


@pytest.mark.parametrize(
    "service_cls,expected_component",
    [(STTService, "STT"), (LLMService, "LLM"), (TTSService, "TTS")],
)
async def test_error_frame_records_runtime_failure_for_known_component(
    db_session_committed, service_cls, expected_component
):
    tap = _make_tap()
    frame = ErrorFrame(
        error="simulated failure",
        processor=MagicMock(spec=service_cls),
        exception=TimeoutError("simulated timeout"),
    )

    await tap.process_frame(frame, FrameDirection.DOWNSTREAM)

    result = await db_session_committed.execute(
        select(RuntimeFailureEvent).where(RuntimeFailureEvent.call_id == "CALL-RTF-TEST")
    )
    row = result.scalar_one()
    assert row.component == expected_component
    assert row.failure_type == "TimeoutError"


async def test_error_frame_from_unrelated_processor_not_recorded(db_session_committed):
    tap = _make_tap()
    frame = ErrorFrame(error="unrelated", processor=MagicMock())  # not STT/LLM/TTS

    await tap.process_frame(frame, FrameDirection.DOWNSTREAM)

    result = await db_session_committed.execute(
        select(RuntimeFailureEvent).where(RuntimeFailureEvent.call_id == "CALL-RTF-TEST")
    )
    assert result.scalar_one_or_none() is None


async def test_non_error_frame_does_not_record_runtime_failure(db_session_committed):
    tap = _make_tap()
    frame = TranscriptionFrame(text="", user_id="u1", timestamp="")

    await tap.process_frame(frame, FrameDirection.DOWNSTREAM)

    result = await db_session_committed.execute(
        select(RuntimeFailureEvent).where(RuntimeFailureEvent.call_id == "CALL-RTF-TEST")
    )
    assert result.scalar_one_or_none() is None
