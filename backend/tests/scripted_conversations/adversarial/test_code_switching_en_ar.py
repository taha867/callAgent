"""AdversarialScenarioId.CODE_SWITCHING_EN_AR — "English and Arabic in the same call
(code-switching, Arabizi)." spec §2.2.3: voice/pipeline.py's _ConversationTapProcessor
persists a detected language change per turn via _persist_language, which updates the
CallSession row callDetail views read.
"""

import asyncio

from sqlalchemy import select

from src.calls.models import CallSession
from src.calls.workflows import CallSessionWorkflow
from src.voice.pipeline import CallPipelineContext, _ConversationTapProcessor
from tests.scripted_conversations.conftest import _seed_customer_and_claim, _start


async def test_a_mid_call_language_switch_is_persisted_on_the_call_session(
    worker, temporal_env, db_session_committed
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="CODESWITCH")
    call_id = "CALL-P4SC-CODESWITCH"
    handle = await _start(temporal_env, call_id, seeded)

    # Poll until CallSession actually exists — the workflow only sets its own state to
    # RIGHT_PARTY_CHECK AFTER the create_call_session activity completes (calls/workflows.py
    # run()), so that's the precise state to wait for, not just "past CALL_QUEUED."
    for _ in range(50):
        if await handle.query(CallSessionWorkflow.current_state) == "RIGHT_PARTY_CHECK":
            break
        await asyncio.sleep(0.1)

    ctx = CallPipelineContext(
        call_id=call_id,
        customer_id=seeded["customer_id"],
        claim_id=seeded["claim_id"],
        workflow_handle=handle,
    )
    tap = _ConversationTapProcessor(ctx, llm_context=None)
    await tap._persist_language("ar")

    row = (
        (
            await db_session_committed.execute(
                select(CallSession).where(CallSession.call_attempt_id == call_id)
            )
        )
        .scalars()
        .one()
    )
    assert row.language == "ar"

    await handle.signal(CallSessionWorkflow.call_dropped)
    await handle.result()
