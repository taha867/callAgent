"""Demo 7 — Multi-Turn Questions (spec §29). Authenticated customer asks a follow-up
question after status delivery -> ASK_QUESTION -> SUCCESS_STATUS_AND_QUERY_RESOLVED.

Note: _run_status_and_follow_up only waits for ONE signal after delivering status before
finalizing (src/calls/workflows.py) — the current workflow does not yet support looping
through several follow-up turns in one call. This test exercises the one follow-up turn the
workflow actually supports today, rather than asserting a multi-turn loop that doesn't
exist — see .claude/specs/phase-4-backend-spec.md §0.2's discipline of testing real
behavior, not aspirational behavior.
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


async def test_demo_7_multi_turn_questions(
    worker, temporal_env, db_session_committed, report_journey_run
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DEMO7")
    call_id = "CALL-P4SC-DEMO7"
    handle = await _start(temporal_env, call_id, seeded)
    await _authenticate_to_follow_up(handle)
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="ASK_QUESTION", topic="ETA"),
    )

    result = await handle.result()
    passed = result.disposition_code == DispositionCode.SUCCESS_STATUS_AND_QUERY_RESOLVED.value
    await report_journey_run(
        demo_journey_id=DemoJourneyId.DEMO_7_MULTI_TURN_QUESTIONS.value,
        passed=passed,
        test_node_id="tests/scripted_conversations/journeys/test_demo_7_multi_turn_questions.py::test_demo_7_multi_turn_questions",
    )
    assert passed
