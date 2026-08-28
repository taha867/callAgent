"""Drives calls/activities.py::persist_transcript_turn directly — standing in for
voice/pipeline.py's direct (non-workflow) call site, same harness discipline
tests/integration/test_phase2_pipeline_signal_bridge.py established for the signal bridge.
No real audio/STT — a fabricated Emirates ID in the "raw_text" input is what proves the
redaction pipeline actually runs before the only INSERT into call_transcript exists in this
codebase (spec §36 rule 17).
"""

import pytest
from sqlalchemy import select

from src.calls.activities import PersistTranscriptTurnInput, persist_transcript_turn
from src.calls.models import CallTranscript
from src.privacy.models import PiiRedactionEvent
from tests.unit.test_phase3_insert_only import _seed_call_attempt

pytestmark = pytest.mark.integration


async def test_persist_transcript_turn_redacts_before_persisting(
    db_session_committed,
):
    attempt = await _seed_call_attempt(db_session_committed, suffix="PIPE-PII")
    await db_session_committed.commit()

    await persist_transcript_turn(
        PersistTranscriptTurnInput(
            call_attempt_id=attempt.id,
            turn_index=0,
            speaker="CUSTOMER",
            raw_text="My Emirates ID is 784-1985-1234567-1, please note it.",
            language="en",
        )
    )

    result = await db_session_committed.execute(
        select(CallTranscript).where(CallTranscript.call_attempt_id == attempt.id)
    )
    turn = result.scalar_one()
    assert "784-1985-1234567-1" not in turn.redacted_text
    assert "[EMIRATES_ID_REDACTED]" in turn.redacted_text

    pii_result = await db_session_committed.execute(
        select(PiiRedactionEvent).where(PiiRedactionEvent.call_id == attempt.id)
    )
    events = pii_result.scalars().all()
    assert len(events) == 1
    assert events[0].category.value == "EMIRATES_ID"
    assert events[0].turn_index == 0


async def test_persist_transcript_turn_no_detections_no_pii_event(db_session_committed):
    attempt = await _seed_call_attempt(db_session_committed, suffix="PIPE-CLEAN")
    await db_session_committed.commit()

    await persist_transcript_turn(
        PersistTranscriptTurnInput(
            call_attempt_id=attempt.id,
            turn_index=0,
            speaker="CUSTOMER",
            raw_text="What's the status of my claim?",
            language="en",
        )
    )

    transcript_result = await db_session_committed.execute(
        select(CallTranscript).where(CallTranscript.call_attempt_id == attempt.id)
    )
    turn = transcript_result.scalar_one()
    assert turn.redacted_text == "What's the status of my claim?"

    pii_result = await db_session_committed.execute(
        select(PiiRedactionEvent).where(PiiRedactionEvent.call_id == attempt.id)
    )
    assert pii_result.scalars().all() == []
