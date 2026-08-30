"""AdversarialScenarioId.VENDOR_TIMEOUT_MID_CALL — merges "LLM timeout mid-call" and
"LLM/STT/TTS timeout mid-call" (spec §5.3): voice/pipeline.py's `_ConversationTapProcessor.
_tag_runtime_failure` classifies which vendor component an ErrorFrame came from and records
a RuntimeFailureEvent — parametrized over all three components here.

Minimal concrete STTService/TTSService subclasses are required only because the real base
classes are ABCs (run_stt/run_tts are abstract) — LLMService has no abstract methods and is
instantiated directly.
"""

from collections.abc import AsyncGenerator

import pytest
from pipecat.frames.frames import ErrorFrame, Frame
from pipecat.services.llm_service import LLMService
from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService
from sqlalchemy import select

from src.audit.models import RuntimeFailureEvent
from src.voice.pipeline import CallPipelineContext, _ConversationTapProcessor
from tests.scripted_conversations.conftest import _seed_customer_and_claim, _start


class _FakeSTTService(STTService):
    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        yield None


class _FakeTTSService(TTSService):
    async def run_tts(self, text: str) -> AsyncGenerator[Frame | None, None]:
        yield None


_PROCESSOR_BY_COMPONENT = {
    "STT": _FakeSTTService,
    "LLM": LLMService,
    "TTS": _FakeTTSService,
}


@pytest.mark.parametrize("component", ["STT", "LLM", "TTS"])
async def test_vendor_timeout_records_a_runtime_failure_event_for_the_right_component(
    worker, temporal_env, db_session_committed, component
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix=f"TIMEOUT{component}")
    call_id = f"CALL-P4SC-TIMEOUT-{component}"
    handle = await _start(temporal_env, call_id, seeded)

    ctx = CallPipelineContext(
        call_id=call_id,
        customer_id=seeded["customer_id"],
        claim_id=seeded["claim_id"],
        workflow_handle=handle,
    )
    tap = _ConversationTapProcessor(ctx, llm_context=None)

    processor = _PROCESSOR_BY_COMPONENT[component]()
    frame = ErrorFrame(error="timeout", processor=processor, exception=TimeoutError("vendor call timed out"))
    await tap._tag_runtime_failure(frame)

    row = (
        (
            await db_session_committed.execute(
                select(RuntimeFailureEvent).where(RuntimeFailureEvent.call_id == call_id)
            )
        )
        .scalars()
        .one()
    )
    assert row.component == component
    assert row.failure_type == "TimeoutError"

    # Clean up the still-running workflow rather than leaving it open until its 60s
    # execution_timeout — call_dropped is the same "abandon this call" path a real dropped
    # call takes.
    from src.calls.workflows import CallSessionWorkflow

    await handle.signal(CallSessionWorkflow.call_dropped)
    await handle.result()
