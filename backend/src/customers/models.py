"""Customer, CustomerContactPreference, CustomerAuthFactor. CommunicationSuppression
remains deferred — see .claude/specs/phase-1-backend-spec.md decision 0.4: the eligibility
check hardcodes "not suppressed" for Phase 1, since the live "stop calling me" interrupt
needs conversation understanding (Phase 2) and suppression-scope policy is Phase 5's."""

from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base


class Customer(Base):
    __tablename__ = "customer"

    id: Mapped[str] = mapped_column(primary_key=True)
    full_name: Mapped[str]
    phone_e164: Mapped[str] = mapped_column(index=True)
    preferred_language: Mapped[str] = mapped_column(default="en")  # "en" | "ar"
    national_id_last4: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CustomerContactPreference(Base):
    __tablename__ = "customer_contact_preference"

    id: Mapped[str] = mapped_column(primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customer.id"), index=True, unique=True)
    preferred_language: Mapped[str] = mapped_column(default="en")  # "en" | "ar"
    preferred_contact_window_start: Mapped[str | None] = mapped_column(default=None)  # "HH:MM"
    preferred_contact_window_end: Mapped[str | None] = mapped_column(default=None)


class CustomerAuthFactor(Base):
    """One row per Level-1 knowledge factor the customer has on file. `factor_value_hash`
    only — spec §10.2's factors (partial Emirates ID, birth month/year, partial plate) are
    never stored or compared in plaintext, same discipline as OTP (§36 rule 18's spirit)."""

    __tablename__ = "customer_auth_factor"

    id: Mapped[str] = mapped_column(primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customer.id"), index=True)
    factor_type: Mapped[str]  # "EID_LAST4" | "BIRTH_MONTH_YEAR" | "PLATE_LAST4"
    factor_value_hash: Mapped[str]  # sha256, same fingerprint helper as src/idempotency.py
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
