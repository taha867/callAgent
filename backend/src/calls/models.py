"""CallAttempt, CallSession — spec §26. Two tables, not one — see
.claude/specs/phase-1-backend-spec.md decision 0.3:

- CallAttempt: one row per dial, created before dialing, covering spec §6.10's no-answer
  data model plus spec §23's structured outcome fields. Exists even for
  NO_ANSWER/VOICEMAIL/CONCURRENT_CALL_CONFLICT attempts — the final activity of
  CallSessionWorkflow always writes to this row, successful or not.
- CallSession: created only when a CallAttempt reaches HumanAnswered, covering spec
  §10.6.2's persisted recovery-state shape. 1:0..1 with its owning CallAttempt.
"""

import uuid
from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.calls.constants import DispositionCode
from src.insert_only import enforce_insert_only
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
    # Phase 2, spec §2.2.3 — "store detected language per turn for QA." Current-language
    # only (not full per-turn history — that's CallTranscript's job below, Phase 3); written
    # directly by voice/pipeline.py via calls/service.py::update_call_session_language(),
    # never through a Temporal activity — see .claude/specs/phase-2-backend-spec.md §0.7.
    language: Mapped[str] = mapped_column(default="en")
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


@enforce_insert_only
class CallTranscript(Base):
    """Phase 3, spec §26/§28 — the "Approved Redacted Transcript Store." One row per turn,
    written ONLY by calls/service.py::record_transcript_turn(), which is called ONLY from
    calls/activities.py::persist_transcript_turn() after privacy/service.py::redact() has
    already run — redacted_text must never be raw STT/TTS output (spec §36 rule 17,
    tests/unit/test_no_unredacted_transcript_writes.py enforces this mechanically).

    turn_index is ONE shared, monotonically-increasing counter across BOTH CUSTOMER and
    AI-authored rows for the same call, not a per-speaker counter — reporting/service.py's
    "initial sentiment = row with MIN(turn_index)" query (spec §31) only makes sense if
    turn_index is globally orderable across the whole call. Do not change this to a
    per-speaker counter without updating that query.

    The unique constraint guards against a duplicated direct-call write (e.g. a WebRTC
    reconnect replaying a frame) — .claude/specs/phase-3-backend-implementation-plan.md
    Correction 2. A dropped write (one lost turn) is accepted as a non-customer-impacting
    risk per that same plan; a silently duplicated one is not.
    """

    __tablename__ = "call_transcript"
    __table_args__ = (
        UniqueConstraint(
            "call_attempt_id",
            "turn_index",
            "speaker",
            name="call_transcript_call_attempt_id_turn_index_speaker_key",
        ),
    )

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    call_attempt_id: Mapped[str] = mapped_column(ForeignKey("call_attempt.id"), index=True)
    turn_index: Mapped[int]
    speaker: Mapped[str]  # "CUSTOMER" | "AI"
    redacted_text: Mapped[str]  # ONLY ever the output of privacy/service.py::redact()
    language: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


@enforce_insert_only
class CallSummary(Base):
    """Phase 3, spec §26 — one row per call, generated post-call by
    calls/activities.py::generate_call_summary() from CallAttempt + CustomerIntent rows
    ONLY, never from CallTranscript (spec §0.7 — never re-deriving new facts from raw
    speech). summary_text is defensively re-redacted before being persisted."""

    __tablename__ = "call_summary"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    call_attempt_id: Mapped[str] = mapped_column(
        ForeignKey("call_attempt.id"), index=True, unique=True
    )
    summary_text: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


@enforce_insert_only
class CustomerIntent(Base):
    """Phase 3, spec §26 — the durable record of a CustomerIntentSignal
    (calls/schemas.py) the workflow consumed. `intent` mirrors IntentName's literal values,
    stored as a plain string (not a DB-level enum) since IntentName grows independently of
    this table and isn't itself spec-cross-checked the way DispositionCode/ActionCode are."""

    __tablename__ = "customer_intent"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    call_attempt_id: Mapped[str] = mapped_column(ForeignKey("call_attempt.id"), index=True)
    intent: Mapped[str]
    topic: Mapped[str | None] = mapped_column(default=None)
    summary: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


@enforce_insert_only
class SentimentEvent(Base):
    """Phase 3, spec §18/§26/§31. `turn_index=None` marks a call-level row (the call-start
    REPEATED_CONTACT fact, or the call-end summary-level sentiment written alongside
    CallSummary) rather than a per-turn read. `sentiment`/`signal` are independently
    optional: a plain polarity read (e.g. NEGATIVE, no named signal) happens on almost every
    turn a customer speaks; a named `signal` (one of spec §18's 7 names) is rarer."""

    __tablename__ = "sentiment_event"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    call_attempt_id: Mapped[str] = mapped_column(ForeignKey("call_attempt.id"), index=True)
    turn_index: Mapped[int | None] = mapped_column(default=None)
    sentiment: Mapped[str | None] = mapped_column(default=None)  # POSITIVE|NEUTRAL|NEGATIVE
    signal: Mapped[str | None] = mapped_column(default=None)  # spec §18's 7 signal names
    confidence: Mapped[float] = mapped_column(default=1.0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


@enforce_insert_only
class CallLatencySample(Base):
    """Phase 3, spec §31 — end-of-speech to first-audio, measured directly by a
    voice/pipeline.py tap (independent of Pipecat's own OpenTelemetry tracing, which is not
    a Postgres-queryable dashboard data source — .claude/specs/phase-3-backend-spec.md
    §0.9). reporting/service.py computes P50/P95/P99 from this table via
    percentile_cont(...)."""

    __tablename__ = "call_latency_sample"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    call_attempt_id: Mapped[str] = mapped_column(ForeignKey("call_attempt.id"), index=True)
    turn_index: Mapped[int]
    latency_ms: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
