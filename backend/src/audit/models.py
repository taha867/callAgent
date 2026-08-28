"""AuditEvent — spec §32's decision/reason_code/policy_rule/action_taken shape, insert-only.

Insert-only is enforced in three independent layers (CLAUDE.md §2.5, spec §36 rule 10):

  1. Service layer (src/audit/service.py) — the module exposes exactly one public callable,
     `record_event()`. There is no update/delete function to call.
  2. ORM layer, here — mapper-level `before_update`/`before_delete` listeners block
     per-instance mutation, and a Session-level `do_orm_execute` listener additionally
     blocks *bulk* UPDATE/DELETE statements against AuditEvent, which mapper-level events
     don't see (a real gap the spec's literal "two ways" doesn't cover).
  3. Database layer — migrations/versions/*_audit_event_insert_only_grants.py REVOKEs
     UPDATE, DELETE, TRUNCATE on audit_event from the runtime app role. This is the real
     backstop: it holds even against a raw SQL script or a future admin tool that bypasses
     the ORM entirely.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.orm.mapper import Mapper
from sqlalchemy.sql import func

from src.exceptions import AuditEventImmutableError
from src.insert_only import enforce_insert_only
from src.models import Base


class AuditEvent(Base):
    __tablename__ = "audit_event"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    call_id: Mapped[str | None] = mapped_column(index=True, default=None)
    correlation_id: Mapped[str | None] = mapped_column(index=True, default=None)
    actor: Mapped[str] = mapped_column(default="SYSTEM")  # "SYSTEM" | "AI" | "HUMAN"
    decision: Mapped[str]
    reason_code: Mapped[str]
    policy_rule: Mapped[str | None] = mapped_column(default=None)
    action_taken: Mapped[str | None] = mapped_column(default=None)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


@event.listens_for(AuditEvent, "before_update", propagate=True)
def _block_instance_update(mapper: Mapper, connection: Any, target: AuditEvent) -> None:
    raise AuditEventImmutableError("audit_event rows cannot be updated (append-only)")


@event.listens_for(AuditEvent, "before_delete", propagate=True)
def _block_instance_delete(mapper: Mapper, connection: Any, target: AuditEvent) -> None:
    raise AuditEventImmutableError("audit_event rows cannot be deleted (append-only)")


@event.listens_for(Session, "do_orm_execute")
def _block_bulk_mutation(orm_execute_state: Any) -> None:
    if not (orm_execute_state.is_update or orm_execute_state.is_delete):
        return
    for desc in orm_execute_state.all_mappers:
        if desc.mapper.class_ is AuditEvent:
            raise AuditEventImmutableError(
                "bulk UPDATE/DELETE against audit_event is not allowed (append-only)"
            )


@enforce_insert_only
class RuntimeFailureEvent(Base):
    """Runtime/model/backend failure + recovery record — spec §10.6, task 10. Lives here,
    not in calls/, per CLAUDE.md's audit/ package bullet ("AuditEvent, SecurityEvent,
    AccessibilityRoutingEvent, RuntimeFailureEvent, DependencyHealthEvent"). Insert-only via
    the shared src.insert_only guard (ORM layer) plus a hand-written REVOKE migration
    (database layer) — see migrations/versions/*_runtime_failure_and_complaint_sla_insert_only_grants.py.

    call_id is a plain indexed string, not an FK, mirroring AuditEvent.call_id above — a
    failure can be recorded before the owning CallAttempt row is finalized.
    """

    __tablename__ = "runtime_failure_event"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    call_id: Mapped[str | None] = mapped_column(index=True, default=None)
    component: Mapped[str]  # "LLM" | "STT" | "TTS" | "BACKEND" | "ORCHESTRATOR" | "TELEPHONY"
    failure_type: Mapped[str]  # spec §10.6's LLM_TIMEOUT | BACKEND_5XX | ... vocabulary
    recovery_action: Mapped[
        str
    ]  # WARM_TRANSFER_IF_AVAILABLE | HUMAN_CALLBACK_CREATED | SAFE_TERMINATION
    consumed_retry_attempt: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
