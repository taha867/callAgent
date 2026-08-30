"""Demo 6 — Delayed Claim / Dissatisfied Customer (spec §29). Authenticated customer,
seeded against a claim with delay_flag=True, expresses dissatisfaction -> the DISSATISFIED
branch's spec §0.8 fix (phase-3-backend-spec.md) checks the claim's real delay_flag and
creates a CLAIM_DELAY_ESCALATION action (not the CLAIMS_TEAM_QUERY fallback it would create
for a non-delayed claim) -> SUCCESS_ACTION_CREATED.
"""

from sqlalchemy import select

from src.actions.constants import ActionCode
from src.actions.models import ClaimAction
from src.calls.constants import DispositionCode
from src.calls.schemas import CustomerIntentSignal
from src.calls.workflows import CallSessionWorkflow
from src.qa.constants import DemoJourneyId
from tests.scripted_conversations.conftest import (
    _authenticate_to_follow_up,
    _seed_customer_and_claim,
    _start,
)


async def test_demo_6_delayed_claim_dissatisfied_customer(
    worker, temporal_env, db_session_committed, report_journey_run
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DEMO6", delay_flag=True)
    call_id = "CALL-P4SC-DEMO6"
    handle = await _start(temporal_env, call_id, seeded)
    await _authenticate_to_follow_up(handle)
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="DISSATISFIED", summary="This is taking too long"),
    )

    result = await handle.result()
    passed = result.disposition_code == DispositionCode.SUCCESS_ACTION_CREATED.value
    if passed:
        row = (
            (
                await db_session_committed.execute(
                    select(ClaimAction).where(ClaimAction.claim_id == seeded["claim_id"])
                )
            )
            .scalars()
            .one()
        )
        passed = row.action_code == ActionCode.CLAIM_DELAY_ESCALATION

    await report_journey_run(
        demo_journey_id=DemoJourneyId.DEMO_6_DELAYED_CLAIM_DISSATISFIED_CUSTOMER.value,
        passed=passed,
        test_node_id="tests/scripted_conversations/journeys/test_demo_6_delayed_claim_dissatisfied.py::test_demo_6_delayed_claim_dissatisfied_customer",
    )
    assert passed
