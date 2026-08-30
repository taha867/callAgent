"""AdversarialScenarioId.CALL_DROP_PRE_POST_AUTH — resolve_disposition checks call_dropped
FIRST, before final_state, and branches on was_authenticated (src/calls/disposition.py) ->
CALL_DROPPED_PRE_AUTH vs CALL_DROPPED_POST_AUTH.
"""

from src.calls.constants import DispositionCode
from src.calls.workflows import CallSessionWorkflow
from tests.scripted_conversations.conftest import (
    _authenticate_to_follow_up,
    _seed_customer_and_claim,
    _start,
)


async def test_call_dropped_before_authentication(worker, temporal_env, db_session_committed):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DROPPRE")
    call_id = "CALL-P4SC-DROPPRE"
    handle = await _start(temporal_env, call_id, seeded)
    await handle.signal(CallSessionWorkflow.call_dropped)

    result = await handle.result()
    assert result.disposition_code == DispositionCode.CALL_DROPPED_PRE_AUTH.value


async def test_call_dropped_after_authentication(worker, temporal_env, db_session_committed):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DROPPOST")
    call_id = "CALL-P4SC-DROPPOST"
    handle = await _start(temporal_env, call_id, seeded)
    await _authenticate_to_follow_up(handle)
    await handle.signal(CallSessionWorkflow.call_dropped)

    result = await handle.result()
    assert result.disposition_code == DispositionCode.CALL_DROPPED_POST_AUTH.value
