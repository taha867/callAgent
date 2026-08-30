"""Demo 3 — Wrong Person (spec §29). Whoever answers is not the customer -> WRONG_PARTY,
no authentication ever attempted.
"""

from src.calls.constants import DispositionCode
from src.calls.schemas import CustomerIntentSignal
from src.calls.workflows import CallSessionWorkflow
from src.qa.constants import DemoJourneyId
from tests.scripted_conversations.conftest import _seed_customer_and_claim, _start


async def test_demo_3_wrong_person(worker, temporal_env, db_session_committed, report_journey_run):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DEMO3")
    call_id = "CALL-P4SC-DEMO3"
    handle = await _start(temporal_env, call_id, seeded)
    await handle.signal(
        CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="WRONG_PARTY")
    )

    result = await handle.result()
    passed = result.disposition_code == DispositionCode.WRONG_PARTY.value
    await report_journey_run(
        demo_journey_id=DemoJourneyId.DEMO_3_WRONG_PERSON.value,
        passed=passed,
        test_node_id="tests/scripted_conversations/journeys/test_demo_3_wrong_person.py::test_demo_3_wrong_person",
    )
    assert passed
