"""AdversarialScenarioId.CONCURRENT_CALL_COLLISION — spec §4.1's distributed voice lock:
Temporal itself rejects a second CallSessionWorkflow execution for the same
workflow_id (derived from customer_id), no separate lock table.
"""

from temporalio.exceptions import TemporalError

from tests.scripted_conversations.conftest import _seed_customer_and_claim, _start


async def test_a_second_concurrent_call_for_the_same_customer_is_rejected(
    worker, temporal_env, db_session_committed
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="COLLISION")
    first_handle = await _start(temporal_env, "CALL-P4SC-COLLISION-1", seeded)

    collided = False
    try:
        await _start(temporal_env, "CALL-P4SC-COLLISION-2", seeded)
    except TemporalError:
        collided = True

    assert collided

    # Clean up the first (still-running) workflow rather than leaving it open.
    from src.calls.workflows import CallSessionWorkflow

    await first_handle.signal(CallSessionWorkflow.call_dropped)
    await first_handle.result()
