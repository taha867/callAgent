"""ClaimAction, Escalation, Callback — spec §21/§25/§26.

Escalation.call_id and Callback are plain indexed strings/FKs per their own shape (spec §19,
§9) — Escalation.call_id is not an FK because it may reference an in-flight
CallSessionWorkflow's call_id before the corresponding CallAttempt row is finalized, the
same reasoning src/audit/models.py's AuditEvent.call_id already documents in Phase 0.

All three `id` columns default to a generated UUID, not a caller-supplied business ID —
these rows are minted entirely by actions/service.py (Batch 8), the same shape as
AuditEvent's/VerificationAttempt's own id default, not an externally-referenced entity like
Customer/MotorClaim.
"""

import uuid
from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.actions.constants import ActionCode
from src.models import Base


class ClaimAction(Base):
    __tablename__ = "claim_action"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    claim_id: Mapped[str] = mapped_column(ForeignKey("motor_claim.id"), index=True)
    source_call_id: Mapped[str | None] = mapped_column(default=None)
    action_code: Mapped[ActionCode] = mapped_column(
        SAEnum(
            ActionCode,
            name="action_code",
            validate_strings=True,
            native_enum=False,
            create_constraint=True,
            length=64,
        )
    )
    summary: Mapped[str]
    status: Mapped[str] = mapped_column(default="OPEN")  # OPEN | CLOSED
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Escalation(Base):
    __tablename__ = "escalation"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    call_id: Mapped[str] = mapped_column(index=True)
    reason: Mapped[str]
    context_snapshot: Mapped[dict] = mapped_column(JSONB)  # spec §19.1 warm-transfer context
    status: Mapped[str] = mapped_column(default="OPEN")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Callback(Base):
    __tablename__ = "callback"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id: Mapped[str] = mapped_column(ForeignKey("customer.id"), index=True)
    claim_id: Mapped[str | None] = mapped_column(default=None)
    callback_window_start: Mapped[datetime]
    callback_window_end: Mapped[datetime]
    reason: Mapped[str]  # "CUSTOMER_DRIVING" | "CUSTOMER_UNAVAILABLE" | ...
    status: Mapped[str] = mapped_column(default="SCHEDULED")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
