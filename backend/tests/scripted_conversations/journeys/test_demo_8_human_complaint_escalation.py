"""Demo 8 — Human / Complaint Escalation (spec §29). Authenticated customer registers a
formal complaint -> COMPLAINT_REQUEST creates a Complaint row and starts
ComplaintSlaMonitorWorkflow as an ABANDON-policy child -> SUCCESS_COMPLAINT_REGISTERED.
"""

from sqlalchemy import select

from src.calls.constants import DispositionCode
from src.calls.schemas import CustomerIntentSignal
from src.calls.workflows import CallSessionWorkflow
from src.complaints.models import Complaint
from src.qa.constants import DemoJourneyId
from tests.scripted_conversations.conftest import (
    _authenticate_to_follow_up,
    _seed_customer_and_claim,
    _start,
)


async def test_demo_8_human_complaint_escalation(
    worker, temporal_env, db_session_committed, report_journey_run
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DEMO8")
    call_id = "CALL-P4SC-DEMO8"
    handle = await _start(temporal_env, call_id, seeded)
    await _authenticate_to_follow_up(handle)
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(
            intent="COMPLAINT_REQUEST",
            complaint_category="REPAIR_QUALITY",
            summary="The repair work is substandard",
            severity="HIGH",
        ),
    )

    result = await handle.result()
    passed = result.disposition_code == DispositionCode.SUCCESS_COMPLAINT_REGISTERED.value
    if passed:
        row = (
            (
                await db_session_committed.execute(
                    select(Complaint).where(Complaint.claim_id == seeded["claim_id"])
                )
            )
            .scalars()
            .one()
        )
        passed = row.severity == "HIGH"

    await report_journey_run(
        demo_journey_id=DemoJourneyId.DEMO_8_HUMAN_COMPLAINT_ESCALATION.value,
        passed=passed,
        test_node_id="tests/scripted_conversations/journeys/test_demo_8_human_complaint_escalation.py::test_demo_8_human_complaint_escalation",
    )
    assert passed
