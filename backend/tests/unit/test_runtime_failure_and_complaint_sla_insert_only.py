"""Mirrors tests/unit/test_audit_insert_only.py's pattern for the two Phase 1 insert-only
tables — runtime_failure_event (src/audit/models.py) and complaint_sla_event
(src/complaints/models.py) — both guarded by the shared src.insert_only mechanism rather
than audit_event's own hand-written listeners. Written before the grant-extension migration
per .claude/specs/phase-1-backend-implementation-plan.md Batch 3.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError, ProgrammingError

from src.audit.models import RuntimeFailureEvent
from src.complaints.models import Complaint, ComplaintSlaEvent
from src.exceptions import InsertOnlyTableViolationError


async def _seed_complaint(db_session, *, suffix: str) -> Complaint:
    from src.claims.constants import ClaimStage
    from src.claims.models import MotorClaim, MotorPolicy
    from src.customers.models import Customer

    db_session.add(Customer(id=f"CUST-SLA-{suffix}", full_name="x", phone_e164="+1"))
    await db_session.flush()
    db_session.add(
        MotorPolicy(
            id=f"POL-SLA-{suffix}",
            customer_id=f"CUST-SLA-{suffix}",
            policy_number="P1",
            vehicle_plate="X",
            vehicle_make_model="Y",
        )
    )
    await db_session.flush()
    db_session.add(
        MotorClaim(
            id=f"CLM-SLA-{suffix}",
            policy_id=f"POL-SLA-{suffix}",
            customer_id=f"CUST-SLA-{suffix}",
            claim_stage=ClaimStage.CLAIM_DELAYED,
            language="en",
        )
    )
    await db_session.flush()
    now = datetime.now(UTC).replace(tzinfo=None)  # naive — matches the plain DateTime() columns
    complaint = Complaint(
        id=f"COMP-SLA-{suffix}",
        claim_id=f"CLM-SLA-{suffix}",
        source_call_id="CALL-SLA-TEST",
        complaint_category="CLAIM_DELAY",
        customer_statement_summary="test",
        severity="MEDIUM",
        preferred_contact_method="PHONE",
        acknowledgment_due_at=now + timedelta(hours=24),
        resolution_due_at=now + timedelta(days=9),
    )
    db_session.add(complaint)
    await db_session.flush()
    return complaint


async def test_runtime_failure_event_instance_update_raises(db_session):
    event = RuntimeFailureEvent(
        component="BACKEND",
        failure_type="BACKEND_TIMEOUT",
        recovery_action="SAFE_TERMINATION",
    )
    db_session.add(event)
    await db_session.flush()

    event.recovery_action = "TAMPERED"
    with pytest.raises(InsertOnlyTableViolationError):
        await db_session.flush()


async def test_runtime_failure_event_instance_delete_raises(db_session):
    event = RuntimeFailureEvent(
        component="BACKEND",
        failure_type="BACKEND_TIMEOUT",
        recovery_action="SAFE_TERMINATION",
    )
    db_session.add(event)
    await db_session.flush()

    await db_session.delete(event)
    with pytest.raises(InsertOnlyTableViolationError):
        await db_session.flush()


async def test_runtime_failure_event_bulk_update_raises(db_session):
    db_session.add(
        RuntimeFailureEvent(
            component="BACKEND", failure_type="BACKEND_TIMEOUT", recovery_action="SAFE_TERMINATION"
        )
    )
    await db_session.flush()

    with pytest.raises(InsertOnlyTableViolationError):
        await db_session.execute(
            update(RuntimeFailureEvent).values(recovery_action="BULK_TAMPERED")
        )


async def test_complaint_sla_event_instance_update_raises(db_session):
    complaint = await _seed_complaint(db_session, suffix="UPD")
    sla_event = ComplaintSlaEvent(
        id="CSE-UPD",
        complaint_id=complaint.id,
        event_type="AT_RISK",
        deadline_kind="ACKNOWLEDGMENT",
    )
    db_session.add(sla_event)
    await db_session.flush()

    sla_event.event_type = "TAMPERED"
    with pytest.raises(InsertOnlyTableViolationError):
        await db_session.flush()


async def test_complaint_sla_event_instance_delete_raises(db_session):
    complaint = await _seed_complaint(db_session, suffix="DEL")
    sla_event = ComplaintSlaEvent(
        id="CSE-DEL",
        complaint_id=complaint.id,
        event_type="AT_RISK",
        deadline_kind="ACKNOWLEDGMENT",
    )
    db_session.add(sla_event)
    await db_session.flush()

    await db_session.delete(sla_event)
    with pytest.raises(InsertOnlyTableViolationError):
        await db_session.flush()


async def test_complaint_sla_event_bulk_update_raises(db_session):
    complaint = await _seed_complaint(db_session, suffix="BULK")
    db_session.add(
        ComplaintSlaEvent(
            id="CSE-BULK",
            complaint_id=complaint.id,
            event_type="AT_RISK",
            deadline_kind="ACKNOWLEDGMENT",
        )
    )
    await db_session.flush()

    with pytest.raises(InsertOnlyTableViolationError):
        await db_session.execute(update(ComplaintSlaEvent).values(event_type="BULK_TAMPERED"))


@pytest.mark.integration
@pytest.mark.requires_two_role_db
async def test_app_role_cannot_mutate_runtime_failure_event(db_session_committed, admin_engine):
    async with admin_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO runtime_failure_event "
                "(id, component, failure_type, recovery_action, consumed_retry_attempt) "
                "VALUES ('RFE-ROLE-TEST', 'BACKEND', 'BACKEND_TIMEOUT', 'SAFE_TERMINATION', false)"
            )
        )

    for stmt in (
        "UPDATE runtime_failure_event SET recovery_action='X' WHERE id='RFE-ROLE-TEST'",
        "DELETE FROM runtime_failure_event WHERE id='RFE-ROLE-TEST'",
        "TRUNCATE runtime_failure_event",
    ):
        with pytest.raises((ProgrammingError, DBAPIError)) as exc_info:
            await db_session_committed.execute(text(stmt))
            await db_session_committed.commit()
        assert "permission denied" in str(exc_info.value).lower()
        await db_session_committed.rollback()

    # migrator role retains TRUNCATE — required by db_session_committed's own teardown.
    async with admin_engine.begin() as conn:
        await conn.execute(text("TRUNCATE runtime_failure_event"))


@pytest.mark.integration
@pytest.mark.requires_two_role_db
async def test_app_role_cannot_mutate_complaint_sla_event(db_session_committed, admin_engine):
    complaint = await _seed_complaint(db_session_committed, suffix="ROLE")
    await db_session_committed.commit()

    async with admin_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO complaint_sla_event (id, complaint_id, event_type, deadline_kind) "
                f"VALUES ('CSE-ROLE-TEST', '{complaint.id}', 'AT_RISK', 'ACKNOWLEDGMENT')"
            )
        )

    for stmt in (
        "UPDATE complaint_sla_event SET event_type='X' WHERE id='CSE-ROLE-TEST'",
        "DELETE FROM complaint_sla_event WHERE id='CSE-ROLE-TEST'",
        "TRUNCATE complaint_sla_event",
    ):
        with pytest.raises((ProgrammingError, DBAPIError)) as exc_info:
            await db_session_committed.execute(text(stmt))
            await db_session_committed.commit()
        assert "permission denied" in str(exc_info.value).lower()
        await db_session_committed.rollback()

    async with admin_engine.begin() as conn:
        await conn.execute(text("TRUNCATE complaint_sla_event CASCADE"))
