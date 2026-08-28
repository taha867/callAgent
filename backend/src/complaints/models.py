"""Complaint, ComplaintSlaEvent — spec §18/§18.1/§26.

acknowledgment_due_at/resolution_due_at are computed server-side only, by
complaints/service.py at creation time (see .claude/specs/phase-1-backend-spec.md decision
0.9) — there is deliberately no field for either on ComplaintCreate (CLAUDE.md §2.4).

ComplaintSlaEvent is insert-only, same discipline as AuditEvent (CLAUDE.md §2.5) — an SLA
clock's history must never be edited, only appended to.

Both `id` columns default to a generated UUID, not a caller-supplied business ID — same
reasoning as src/actions/models.py's ClaimAction/Escalation/Callback.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from src.insert_only import enforce_insert_only
from src.models import Base


class Complaint(Base):
    __tablename__ = "complaint"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    claim_id: Mapped[str] = mapped_column(ForeignKey("motor_claim.id"), index=True)
    source_call_id: Mapped[str]
    complaint_category: Mapped[str]
    customer_statement_summary: Mapped[str]
    customer_expected_resolution: Mapped[str | None] = mapped_column(default=None)
    severity: Mapped[str]  # LOW | MEDIUM | HIGH
    preferred_contact_method: Mapped[str]  # PHONE | EMAIL | SMS
    status: Mapped[str] = mapped_column(default="OPEN")
    acknowledgment_due_at: Mapped[datetime]
    resolution_due_at: Mapped[datetime]
    sla_source: Mapped[str] = mapped_column(default="INSURER_CONFIGURED")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


@enforce_insert_only
class ComplaintSlaEvent(Base):
    __tablename__ = "complaint_sla_event"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    complaint_id: Mapped[str] = mapped_column(ForeignKey("complaint.id"), index=True)
    event_type: Mapped[str]  # "AT_RISK" | "BREACHED"
    deadline_kind: Mapped[str]  # "ACKNOWLEDGMENT" | "RESOLUTION"
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())
