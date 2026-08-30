"""Demo 2 — Customer Busy (spec §29). The right party answers but is busy right now
("I'm driving, call me back") -> the existing CUSTOMER_DRIVING branch in
_run_right_party_check schedules a callback before authentication even starts ->
CALLBACK_REQUESTED. This is the closest existing workflow branch to "customer busy";
DispositionCode has no dedicated CUSTOMER_BUSY code (checked calls/constants.py directly).
"""

from src.calls.constants import DispositionCode
from src.calls.schemas import CustomerIntentSignal
from src.calls.workflows import CallSessionWorkflow
from src.qa.constants import DemoJourneyId
from tests.scripted_conversations.conftest import _seed_customer_and_claim, _start


async def test_demo_2_customer_busy(worker, temporal_env, db_session_committed, report_journey_run):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DEMO2")
    call_id = "CALL-P4SC-DEMO2"
    handle = await _start(temporal_env, call_id, seeded)
    await handle.signal(
        CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="CUSTOMER_DRIVING")
    )

    result = await handle.result()
    passed = result.disposition_code == DispositionCode.CALLBACK_REQUESTED.value
    await report_journey_run(
        demo_journey_id=DemoJourneyId.DEMO_2_CUSTOMER_BUSY.value,
        passed=passed,
        test_node_id="tests/scripted_conversations/journeys/test_demo_2_customer_busy.py::test_demo_2_customer_busy",
    )
    assert passed
