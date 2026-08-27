import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError, ProgrammingError

from src.audit import service as audit_service
from src.audit.models import AuditEvent
from src.exceptions import AuditEventImmutableError


def test_service_module_exposes_only_record_event():
    """Layer 1: the service-layer omission. No delete_event/update_event exists to call."""
    public_callables = {
        name
        for name, obj in vars(audit_service).items()
        if not name.startswith("_")
        and callable(obj)
        and getattr(obj, "__module__", None) == audit_service.__name__
    }
    assert public_callables == {"record_event"}


async def test_instance_update_raises(db_session):
    event = await audit_service.record_event(
        db_session, decision="TEST_DECISION", reason_code="TEST_REASON"
    )
    await db_session.flush()

    event.decision = "TAMPERED"
    with pytest.raises(AuditEventImmutableError):
        await db_session.flush()


async def test_instance_delete_raises(db_session):
    event = await audit_service.record_event(
        db_session, decision="TEST_DECISION", reason_code="TEST_REASON"
    )
    await db_session.flush()

    await db_session.delete(event)
    with pytest.raises(AuditEventImmutableError):
        await db_session.flush()


async def test_bulk_update_raises(db_session):
    await audit_service.record_event(
        db_session, decision="TEST_DECISION", reason_code="TEST_REASON"
    )
    await db_session.flush()

    with pytest.raises(AuditEventImmutableError):
        await db_session.execute(update(AuditEvent).values(decision="BULK_TAMPERED"))


async def test_plain_insert_succeeds(db_session):
    event = await audit_service.record_event(
        db_session, decision="SUCCESS_TEST", reason_code="TEST_OK"
    )
    await db_session.flush()
    result = await db_session.execute(
        text("SELECT decision FROM audit_event WHERE id = :id"), {"id": event.id}
    )
    assert result.scalar_one() == "SUCCESS_TEST"


@pytest.mark.integration
@pytest.mark.requires_two_role_db
async def test_app_role_cannot_mutate_audit_event(db_session_committed, admin_engine):
    """Layer 3: as callagent_app, raw UPDATE/DELETE/TRUNCATE against audit_event all fail
    with a Postgres privilege error; the same statements as callagent_migrator succeed —
    proving the REVOKE is role-scoped, not accidental."""
    event = await audit_service.record_event(
        db_session_committed, decision="ROLE_TEST", reason_code="TEST_OK"
    )
    await db_session_committed.commit()
    # Captured before any rollback: a rollback expires every attribute on `event`, and a
    # later bare `event.id` access would need its own implicit DB round-trip outside an
    # awaited context (raises MissingGreenlet) rather than reusing the known-good value.
    event_id = event.id

    for stmt in (
        f"UPDATE audit_event SET decision='X' WHERE id='{event_id}'",
        f"DELETE FROM audit_event WHERE id='{event_id}'",
        "TRUNCATE audit_event",
    ):
        with pytest.raises((ProgrammingError, DBAPIError)) as exc_info:
            await db_session_committed.execute(text(stmt))
            await db_session_committed.commit()
        assert "permission denied" in str(exc_info.value).lower()
        await db_session_committed.rollback()

    async with admin_engine.begin() as conn:
        result = await conn.execute(
            text(
                f"UPDATE audit_event SET decision='ADMIN_TAMPERED' WHERE id='{event_id}' RETURNING decision"
            )
        )
        assert result.scalar_one() == "ADMIN_TAMPERED"
