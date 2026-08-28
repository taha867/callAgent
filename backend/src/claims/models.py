"""MotorPolicy, MotorClaim, ClaimStatusEvent, ClaimDocument, ClaimParty, RepairGarage — the
Authoritative Data Layer (spec §2.3) for the MVP's synthetic demo claims.

`ClaimStage` (imported from claims/constants.py — see that module's docstring for why it
doesn't live here) is typed via `Enum(..., validate_strings=True, native_enum=False)` —
VARCHAR + CHECK, not a native Postgres enum type — per
.claude/specs/phase-0-backend-spec.md decision 5: growing spec §13's status catalogue later
is a one-line ALTER TABLE, not a locking ALTER TYPE. This is the Phase-0 proving ground for
the pattern Phase 1's CallAttempt.disposition_code and Phase 3's ClaimAction.action_code
reuse.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from src.claims.constants import ClaimStage
from src.models import Base


class RepairGarage(Base):
    __tablename__ = "repair_garage"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    phone_e164: Mapped[str | None] = mapped_column(default=None)
    address: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class MotorPolicy(Base):
    __tablename__ = "motor_policy"

    id: Mapped[str] = mapped_column(primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customer.id"), index=True)
    policy_number: Mapped[str] = mapped_column(index=True)
    vehicle_plate: Mapped[str]
    vehicle_make_model: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class MotorClaim(Base):
    """Spec §12's Structured Claim Status Object shape."""

    __tablename__ = "motor_claim"

    id: Mapped[str] = mapped_column(primary_key=True)
    policy_id: Mapped[str] = mapped_column(ForeignKey("motor_policy.id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customer.id"), index=True)
    garage_id: Mapped[str | None] = mapped_column(ForeignKey("repair_garage.id"), default=None)

    claim_stage: Mapped[ClaimStage] = mapped_column(
        SAEnum(
            ClaimStage,
            name="claim_stage",
            validate_strings=True,
            native_enum=False,
            create_constraint=True,
            length=64,
        )
    )
    current_owner: Mapped[str | None] = mapped_column(default=None)
    status_timestamp: Mapped[datetime] = mapped_column(server_default=func.now())
    next_expected_event: Mapped[str | None] = mapped_column(default=None)
    expected_by: Mapped[datetime | None] = mapped_column(default=None)
    customer_action_required: Mapped[bool] = mapped_column(default=False)
    customer_action_code: Mapped[str | None] = mapped_column(default=None)
    delay_flag: Mapped[bool] = mapped_column(default=False)
    approved_customer_message_key: Mapped[str | None] = mapped_column(default=None)
    language: Mapped[str] = mapped_column(default="en")

    # spec §13 Journey E — money pulled from claims data is Decimal, never Float
    # (CLAUDE.md §2.4, §36 non-negotiables).
    settlement_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ClaimStatusEvent(Base):
    __tablename__ = "claim_status_event"

    id: Mapped[str] = mapped_column(primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("motor_claim.id"), index=True)
    # Distinct `name=` per column — two enum-typed columns on the same table sharing the
    # default type name ("claimstage") collide on the naming convention's
    # %(table_name)s_%(constraint_name)s_check CHECK constraint name.
    from_stage: Mapped[ClaimStage | None] = mapped_column(
        SAEnum(
            ClaimStage,
            name="claim_stage_from",
            validate_strings=True,
            native_enum=False,
            create_constraint=True,
            length=64,
        ),
        default=None,
    )
    to_stage: Mapped[ClaimStage] = mapped_column(
        SAEnum(
            ClaimStage,
            name="claim_stage_to",
            validate_strings=True,
            native_enum=False,
            create_constraint=True,
            length=64,
        )
    )
    event_timestamp: Mapped[datetime] = mapped_column(server_default=func.now())
    note: Mapped[str | None] = mapped_column(default=None)


class ClaimDocument(Base):
    __tablename__ = "claim_document"

    id: Mapped[str] = mapped_column(primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("motor_claim.id"), index=True)
    document_type: Mapped[str]
    status: Mapped[str] = mapped_column(default="PENDING")  # PENDING | RECEIVED
    requested_at: Mapped[datetime] = mapped_column(server_default=func.now())
    received_at: Mapped[datetime | None] = mapped_column(default=None)


class ClaimParty(Base):
    __tablename__ = "claim_party"

    id: Mapped[str] = mapped_column(primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("motor_claim.id"), index=True)
    role: Mapped[str]  # POLICYHOLDER | THIRD_PARTY | WITNESS
    full_name: Mapped[str]
    phone_e164: Mapped[str | None] = mapped_column(default=None)
