"""ComplaintSlaMonitorWorkflow — spec §18.1's durable SLA timer, task 7/Batch 15. Started
as a child of CallSessionWorkflow's COMPLAINT_REQUEST branch (see calls/workflows.py); this
file proves the monitor workflow itself, in isolation, using the time-skipping environment
since its waits span real hours/days (complaints/config.py's ACKNOWLEDGMENT_SLA_HOURS/
RESOLUTION_SLA_DAYS/SLA_WARNING_HOURS).
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from temporalio.worker import Worker

from src.actions.constants import ActionCode
from src.actions.models import ClaimAction
from src.calls.activities import ALL_CALLS_ACTIVITIES
from src.complaints.activities import ALL_COMPLAINTS_ACTIVITIES
from src.complaints.models import Complaint, ComplaintSlaEvent
from src.complaints.workflows import ComplaintSlaMonitorInput, ComplaintSlaMonitorWorkflow
from src.workflow_runner import SANDBOXED_WORKFLOW_RUNNER

pytestmark = pytest.mark.integration

_TASK_QUEUE = "complaint-sla-e2e"
_NOW = datetime(2026, 8, 27, 12, 0, 0)


async def _seed_complaint(db, *, suffix: str, ack_hours: int, res_days: int) -> dict:
    from src.claims.constants import ClaimStage
    from src.claims.models import MotorClaim, MotorPolicy
    from src.customers.models import Customer

    customer_id = f"CUST-SLA-{suffix}"
    db.add(Customer(id=customer_id, full_name="x", phone_e164="+1"))
    await db.flush()
    db.add(
        MotorPolicy(
            id=f"POL-SLA-{suffix}",
            customer_id=customer_id,
            policy_number="P1",
            vehicle_plate="X",
            vehicle_make_model="Y",
        )
    )
    await db.flush()
    claim_id = f"CLM-SLA-{suffix}"
    db.add(
        MotorClaim(
            id=claim_id,
            policy_id=f"POL-SLA-{suffix}",
            customer_id=customer_id,
            claim_stage=ClaimStage.CLAIM_DELAYED,
            language="en",
        )
    )
    await db.flush()
    complaint_id = f"COMP-SLA-{suffix}"
    db.add(
        Complaint(
            id=complaint_id,
            claim_id=claim_id,
            source_call_id=f"CALL-SLA-{suffix}",
            complaint_category="CLAIM_DELAY",
            customer_statement_summary="test",
            severity="MEDIUM",
            preferred_contact_method="PHONE",
            acknowledgment_due_at=_NOW + timedelta(hours=ack_hours),
            resolution_due_at=_NOW + timedelta(days=res_days),
        )
    )
    await db.commit()
    return {"complaint_id": complaint_id, "claim_id": claim_id}


async def test_sla_monitor_raises_at_risk_then_breached_for_uncleared_complaint(
    temporal_time_skipping_env, db_session_committed
):
    """Nothing in Phase 1 ever acknowledges/resolves a complaint (spec §18: human-controlled,
    no dashboard yet — see complaints/activities.py's module docstring), so this complaint's
    deadlines are never cleared and the monitor must raise all four events (AT_RISK then
    BREACHED, for both ACKNOWLEDGMENT and RESOLUTION)."""
    seeded = await _seed_complaint(db_session_committed, suffix="FULL", ack_hours=24, res_days=9)

    async with Worker(
        temporal_time_skipping_env.client,
        task_queue=_TASK_QUEUE,
        workflows=[ComplaintSlaMonitorWorkflow],
        activities=[*ALL_CALLS_ACTIVITIES, *ALL_COMPLAINTS_ACTIVITIES],
        workflow_runner=SANDBOXED_WORKFLOW_RUNNER,
    ):
        await temporal_time_skipping_env.client.execute_workflow(
            ComplaintSlaMonitorWorkflow.run,
            ComplaintSlaMonitorInput(
                complaint_id=seeded["complaint_id"],
                claim_id=seeded["claim_id"],
                acknowledgment_due_at=_NOW + timedelta(hours=24),
                resolution_due_at=_NOW + timedelta(days=9),
                warning_hours=4,
            ),
            id=f"complaint-sla-{seeded['complaint_id']}",
            task_queue=_TASK_QUEUE,
            execution_timeout=timedelta(days=30),
        )

    events = (
        (
            await db_session_committed.execute(
                select(ComplaintSlaEvent).where(
                    ComplaintSlaEvent.complaint_id == seeded["complaint_id"]
                )
            )
        )
        .scalars()
        .all()
    )
    seen = {(e.event_type, e.deadline_kind) for e in events}
    assert seen == {
        ("AT_RISK", "ACKNOWLEDGMENT"),
        ("BREACHED", "ACKNOWLEDGMENT"),
        ("AT_RISK", "RESOLUTION"),
        ("BREACHED", "RESOLUTION"),
    }

    actions = (
        (
            await db_session_committed.execute(
                select(ClaimAction).where(ClaimAction.claim_id == seeded["claim_id"])
            )
        )
        .scalars()
        .all()
    )
    assert len(actions) == 4
    assert all(a.action_code == ActionCode.COMPLAINT_SLA_ESCALATION for a in actions)


async def test_sla_monitor_skips_events_once_complaint_is_acknowledged_and_resolved(
    temporal_time_skipping_env, db_session_committed
):
    """A complaint whose status is already RESOLVED before any deadline arrives must not
    raise any SLA event at all — is_deadline_cleared's whole purpose."""
    seeded = await _seed_complaint(db_session_committed, suffix="CLEAR", ack_hours=24, res_days=9)

    complaint = await db_session_committed.get(Complaint, seeded["complaint_id"])
    complaint.status = "RESOLVED"
    await db_session_committed.commit()

    async with Worker(
        temporal_time_skipping_env.client,
        task_queue=_TASK_QUEUE,
        workflows=[ComplaintSlaMonitorWorkflow],
        activities=[*ALL_CALLS_ACTIVITIES, *ALL_COMPLAINTS_ACTIVITIES],
        workflow_runner=SANDBOXED_WORKFLOW_RUNNER,
    ):
        await temporal_time_skipping_env.client.execute_workflow(
            ComplaintSlaMonitorWorkflow.run,
            ComplaintSlaMonitorInput(
                complaint_id=seeded["complaint_id"],
                claim_id=seeded["claim_id"],
                acknowledgment_due_at=_NOW + timedelta(hours=24),
                resolution_due_at=_NOW + timedelta(days=9),
                warning_hours=4,
            ),
            id=f"complaint-sla-{seeded['complaint_id']}",
            task_queue=_TASK_QUEUE,
            execution_timeout=timedelta(days=30),
        )

    events = (
        (
            await db_session_committed.execute(
                select(ComplaintSlaEvent).where(
                    ComplaintSlaEvent.complaint_id == seeded["complaint_id"]
                )
            )
        )
        .scalars()
        .all()
    )
    assert events == []
