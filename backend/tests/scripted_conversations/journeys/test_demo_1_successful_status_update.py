"""Demo 1 — Successful Status Update (spec §29). Cooperative path: right party confirmed,
authenticated, status delivered, customer has nothing else -> SUCCESS_STATUS_DELIVERED.
"""

from src.calls.constants import DispositionCode
from src.calls.schemas import CustomerIntentSignal
from src.calls.workflows import CallSessionWorkflow
from src.qa.constants import DemoJourneyId
from tests.scripted_conversations.conftest import (
    _authenticate_to_follow_up,
    _seed_customer_and_claim,
    _start,
)


async def test_demo_1_successful_status_update(
    worker, temporal_env, db_session_committed, report_journey_run
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DEMO1")
    call_id = "CALL-P4SC-DEMO1"
    handle = await _start(temporal_env, call_id, seeded)
    await _authenticate_to_follow_up(handle)
    await handle.signal(
        CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="NOTHING_ELSE")
    )

    result = await handle.result()
    passed = result.disposition_code == DispositionCode.SUCCESS_STATUS_DELIVERED.value
    await report_journey_run(
        demo_journey_id=DemoJourneyId.DEMO_1_SUCCESSFUL_STATUS_UPDATE.value,
        passed=passed,
        test_node_id="tests/scripted_conversations/journeys/test_demo_1_successful_status_update.py::test_demo_1_successful_status_update",
    )
    assert passed
