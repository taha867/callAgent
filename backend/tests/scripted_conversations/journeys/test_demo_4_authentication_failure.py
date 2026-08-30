"""Demo 4 — Authentication Failure (spec §29). Right party confirmed, but the customer
supplies the wrong birth-year answer MAX_AUTH_ATTEMPTS (2, verification/constants.py) times
in a row -> AUTH_FAILED, never reaching status delivery.
"""

from src.calls.constants import DispositionCode
from src.calls.schemas import CustomerIntentSignal
from src.calls.workflows import CallSessionWorkflow
from src.qa.constants import DemoJourneyId
from src.verification.constants import MAX_AUTH_ATTEMPTS
from tests.scripted_conversations.conftest import _seed_customer_and_claim, _start


async def test_demo_4_authentication_failure(
    worker, temporal_env, db_session_committed, report_journey_run
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DEMO4", factor_value="1990")
    call_id = "CALL-P4SC-DEMO4"
    handle = await _start(temporal_env, call_id, seeded)
    await handle.signal(
        CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="RIGHT_PARTY_CONFIRMED")
    )
    for _ in range(MAX_AUTH_ATTEMPTS):
        await handle.signal(
            CallSessionWorkflow.customer_utterance,
            CustomerIntentSignal(intent="AUTH_ANSWER", value="1975"),  # wrong on purpose
        )

    result = await handle.result()
    passed = result.disposition_code == DispositionCode.AUTH_FAILED.value
    await report_journey_run(
        demo_journey_id=DemoJourneyId.DEMO_4_AUTHENTICATION_FAILURE.value,
        passed=passed,
        test_node_id="tests/scripted_conversations/journeys/test_demo_4_authentication_failure.py::test_demo_4_authentication_failure",
    )
    assert passed
