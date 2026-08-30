"""Demo 9 — No Answer (spec §30, the Ninth Technical Demo). No customer conversation at
all: simulated_answer_result="NO_ANSWER" short-circuits CallSessionWorkflow.run() before
RIGHT_PARTY_CHECK ever starts -> NO_ANSWER disposition, no signals needed.
"""

from src.calls.constants import DispositionCode
from src.qa.constants import DemoJourneyId
from tests.scripted_conversations.conftest import _seed_customer_and_claim, _start


async def test_demo_9_no_answer(worker, temporal_env, db_session_committed, report_journey_run):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DEMO9")
    call_id = "CALL-P4SC-DEMO9"
    handle = await _start(temporal_env, call_id, seeded, simulated_answer_result="NO_ANSWER")

    result = await handle.result()
    passed = result.disposition_code == DispositionCode.NO_ANSWER.value
    await report_journey_run(
        demo_journey_id=DemoJourneyId.DEMO_9_NO_ANSWER.value,
        passed=passed,
        test_node_id="tests/scripted_conversations/journeys/test_demo_9_no_answer.py::test_demo_9_no_answer",
    )
    assert passed
