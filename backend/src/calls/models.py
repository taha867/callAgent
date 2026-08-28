"""CallAttempt, CallSession — spec §26. Two tables, not one — see
.claude/specs/phase-1-backend-spec.md decision 0.3:

- CallAttempt: one row per dial, created before dialing, covering spec §6.10's no-answer
  data model plus spec §23's structured outcome fields. Exists even for
  NO_ANSWER/VOICEMAIL/CONCURRENT_CALL_CONFLICT attempts — the final activity of
  CallSessionWorkflow always writes to this row, successful or not.
- CallSession: created only when a CallAttempt reaches HumanAnswered, covering spec
  §10.6.2's persisted recovery-state shape. 1:0..1 with its owning CallAttempt.
"""

from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from src.calls.constants import DispositionCode
from src.models import Base


class CallAttempt(Base):
    __tablename__ = "call_attempt"

    id: Mapped[str] = mapped_column(primary_key=True)
    call_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("call_job.id"), index=True, default=None
    )
    customer_id: Mapped[str] = mapped_column(ForeignKey("customer.id"), index=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("motor_claim.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(default=1)
    attempted_at: Mapped[datetime] = mapped_column(server_default=func.now())
    answer_result: Mapped[str | None] = mapped_column(default=None)  # spec §5's classification
    # Nullable: the row is created BEFORE dialing (attempt outcome unknown yet) and
    # finalized only once CallSessionWorkflow's terminal activity calls
    # calls/service.py::finalize_outcome() — see .claude/specs/phase-1-backend-spec.md §9.
    disposition_code: Mapped[DispositionCode | None] = mapped_column(
        SAEnum(
            DispositionCode,
            name="disposition_code",
            validate_strings=True,
            native_enum=False,
            create_constraint=True,
            length=64,
        ),
        default=None,
    )

    # spec §23 structured outcome fields
    customer_reached: Mapped[bool] = mapped_column(default=False)
    right_party: Mapped[bool | None] = mapped_column(default=None)
    verified: Mapped[bool] = mapped_column(default=False)
    verification_level: Mapped[str | None] = mapped_column(default=None)
    status_delivered: Mapped[str | None] = mapped_column(default=None)
    resolution: Mapped[str | None] = mapped_column(default=None)
    duration_seconds: Mapped[int | None] = mapped_column(default=None)

    # spec §6.10 retry-engine fields
    next_attempt_at: Mapped[datetime | None] = mapped_column(default=None)
    voicemail_detected: Mapped[bool] = mapped_column(default=False)
    attempts_remaining: Mapped[int | None] = mapped_column(default=None)


class CallSession(Base):
    """Created only on HumanAnswered — see module docstring. Mirrors spec §10.6.2."""

    __tablename__ = "call_session"

    id: Mapped[str] = mapped_column(primary_key=True)
    call_attempt_id: Mapped[str] = mapped_column(
        ForeignKey("call_attempt.id"), index=True, unique=True
    )
    state: Mapped[str]  # CallState value
    right_party_confirmed: Mapped[bool] = mapped_column(default=False)
    verification_level: Mapped[str] = mapped_column(default="L0")
    status_already_disclosed: Mapped[bool] = mapped_column(default=False)
    pending_action: Mapped[str | None] = mapped_column(default=None)
    last_committed_event_id: Mapped[str | None] = mapped_column(default=None)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
