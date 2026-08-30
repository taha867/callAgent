"""AdversarialScenarioId.UNPROMPTED_PII_DISCLOSURE — "customer speaks a full Emirates ID /
IBAN / card number unprompted." privacy/service.py::redact()'s own pure-function behavior is
already thoroughly covered by tests/unit/test_scrubber.py — what that suite does NOT cover is
the actual write path: calls/activities.py::persist_transcript_turn always runs redact()
before the only INSERT into call_transcript (spec §36 rule 17). This test exercises that
activity directly with unprompted, PII-bearing raw text and asserts the PERSISTED row never
contains the raw value.
"""

import asyncio

from sqlalchemy import select

from src.calls.activities import PersistTranscriptTurnInput, persist_transcript_turn
from src.calls.models import CallTranscript
from src.calls.workflows import CallSessionWorkflow
from tests.scripted_conversations.conftest import (
    _authenticate_to_follow_up,
    _seed_customer_and_claim,
    _start,
)

_VALID_IBAN = "AE070331234567890123456"


async def test_unprompted_iban_disclosure_is_redacted_before_persisting(
    worker, temporal_env, db_session_committed
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="PIIDISC")
    call_id = "CALL-P4SC-PIIDISC"
    handle = await _start(temporal_env, call_id, seeded)
    await _authenticate_to_follow_up(handle)

    # Poll until the workflow has actually reached FOLLOW_UP — persist_transcript_turn is a
    # raw activity call outside any workflow signal, so it needs create_call_attempt (run
    # unconditionally at the very start of CallSessionWorkflow.run()) to have already
    # completed, which signal delivery alone doesn't guarantee (a signal is queued, not
    # necessarily processed, by the time handle.signal() returns).
    for _ in range(50):
        if await handle.query(CallSessionWorkflow.current_state) == "FOLLOW_UP":
            break
        await asyncio.sleep(0.1)

    raw_text = f"My IBAN is {_VALID_IBAN}, please refund me directly"
    await persist_transcript_turn(
        PersistTranscriptTurnInput(
            call_attempt_id=call_id,
            turn_index=0,
            speaker="CUSTOMER",
            raw_text=raw_text,
            language="en",
        )
    )

    row = (
        (
            await db_session_committed.execute(
                select(CallTranscript).where(CallTranscript.call_attempt_id == call_id)
            )
        )
        .scalars()
        .one()
    )
    assert _VALID_IBAN not in row.redacted_text
    assert "[IBAN_REDACTED]" in row.redacted_text

    await handle.signal(CallSessionWorkflow.call_dropped)
    await handle.result()
