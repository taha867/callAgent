"""VerificationAttempt, OtpChallenge — spec §10, §26. `code_hash` only on OtpChallenge —
spec §10.3.2/§36 rule 18: never store an OTP value in plaintext.

Both `id` columns default to a generated UUID, not a caller-supplied business ID — unlike
Customer/MotorClaim, these rows are minted entirely by verification/service.py itself, one
per attempt/challenge, the same shape as AuditEvent's own id default.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base


class VerificationAttempt(Base):
    __tablename__ = "verification_attempt"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    call_session_id: Mapped[str] = mapped_column(ForeignKey("call_session.id"), index=True)
    level: Mapped[str]  # "L1" | "L2"
    factor_type: Mapped[str | None] = mapped_column(default=None)
    outcome: Mapped[str]  # "MATCH" | "NO_MATCH"
    attempted_at: Mapped[datetime] = mapped_column(server_default=func.now())


class OtpChallenge(Base):
    __tablename__ = "otp_challenge"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    call_session_id: Mapped[str] = mapped_column(ForeignKey("call_session.id"), index=True)
    code_hash: Mapped[str]
    sent_count: Mapped[int] = mapped_column(default=1)
    attempt_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(default="SENT")  # SENT|VERIFIED|EXPIRED|LOCKED
    expires_at: Mapped[datetime]
    locked_until: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
