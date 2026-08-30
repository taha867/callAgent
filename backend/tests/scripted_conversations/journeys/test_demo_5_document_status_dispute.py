"""Demo 5 — Document Status Dispute (spec §29). Authenticated customer disputes the status
of a submitted document -> DISPUTE_DOCUMENT creates a DOCUMENT_STATUS_DISPUTE ClaimAction ->
SUCCESS_ACTION_CREATED (action_created wins over status_delivered in resolve_disposition's
priority order).
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


async def test_demo_5_document_status_dispute(
    worker, temporal_env, db_session_committed, report_journey_run
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DEMO5")
    call_id = "CALL-P4SC-DEMO5"
    handle = await _start(temporal_env, call_id, seeded)
    await _authenticate_to_follow_up(handle)
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(
            intent="DISPUTE_DOCUMENT",
            document_type="POLICE_REPORT",
            summary="Customer says the police report was already submitted",
        ),
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
        passed = row.action_code == ActionCode.DOCUMENT_STATUS_DISPUTE

    await report_journey_run(
        demo_journey_id=DemoJourneyId.DEMO_5_DOCUMENT_STATUS_DISPUTE.value,
        passed=passed,
        test_node_id="tests/scripted_conversations/journeys/test_demo_5_document_status_dispute.py::test_demo_5_document_status_dispute",
    )
    assert passed
