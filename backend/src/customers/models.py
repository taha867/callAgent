"""Minimal Customer only. CustomerContactPreference/CustomerAuthFactor/
CommunicationSuppression are explicitly deferred to Phase 1+ — see
.claude/specs/phase-0-backend-spec.md §4.1."""

from datetime import datetime

from sqlalchemy import func
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
