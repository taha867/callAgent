"""TelephonyCliConfiguration, BusinessContactCalendar — spec §4.1/§6.1, task 4's "CLI
validation stub, contact-calendar stub". No DistributedVoiceLock model — the distributed
voice lock is Temporal's own workflow-ID uniqueness (calls.workflows.CallSessionWorkflow,
keyed by customer_id) plus a bounded execution_timeout, not a separate table. See
.claude/specs/phase-1-backend-spec.md decision 0.2 for why.
"""

from datetime import date

from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base


class TelephonyCliConfiguration(Base):
    __tablename__ = "telephony_cli_configuration"

    cli: Mapped[str] = mapped_column(primary_key=True)  # "+971XXXXXXXXX"
    owner: Mapped[str]
    trunk_authorized: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)


class BusinessContactCalendar(Base):
    """Stub per task 4 — one row per exceptional day. Absence of a row for a date means
    'normal contact window applies'; real Ramadan/holiday data is a Phase 5 concern."""

    __tablename__ = "business_contact_calendar"

    id: Mapped[str] = mapped_column(primary_key=True)
    calendar_date: Mapped[date] = mapped_column(index=True)
    calendar_type: Mapped[str]  # "HOLIDAY" | "RAMADAN" | "BLACKOUT"
    contact_allowed: Mapped[bool] = mapped_column(default=False)
