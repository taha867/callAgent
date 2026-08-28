"""CallSessionInput/CallSessionOutput/CustomerIntentSignal — shared between
calls/workflows.py and calls/activities.py, defined here (not in either of those modules)
so calls/workflows.py's import graph never has to reach into calls/activities.py (which
pulls in SQLAlchemy/src.database — not sandbox-safe). Imports only `pydantic` — same
workflow-sandbox-safe discipline as calls/constants.py.

CustomerIntentSignal is deliberately not raw text: Phase 1 has no STT/LLM to turn speech
into intent yet, so the fake/text harness supplies the already-classified intent directly —
exactly what Phase 2's real voice/pipeline.py will extract and signal in once it exists. See
.claude/specs/phase-1-backend-spec.md decision 0.5.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

IntentName = Literal[
    "RIGHT_PARTY_CONFIRMED",
    "WRONG_PARTY",
    "CUSTOMER_UNAVAILABLE",
    "CUSTOMER_DRIVING",
    "AUTH_ANSWER",
    "REQUEST_OTP",  # a system decision to step up to Level 2 — see calls/workflows.py
    "OTP_ANSWER",
    "ASK_QUESTION",
    "DISPUTE_DOCUMENT",
    "DISSATISFIED",
    "COMPLAINT_REQUEST",
    "REQUEST_HUMAN",
    "NOTHING_ELSE",
    # Phase 2 — AI-initiated variants bridged from voice/tools.py's tool-dispatch table
    # (.claude/specs/phase-2-backend-spec.md §0.3/§4.2), not customer-utterance-classified.
    "AI_SCHEDULE_CALLBACK",
    "AI_CREATE_ACTION",
    "AI_SEND_SECURE_LINK",
]


class CustomerIntentSignal(BaseModel):
    intent: IntentName
    value: str | None = None  # AUTH_ANSWER / OTP_ANSWER's supplied answer
    # ASK_QUESTION's topic ("GARAGE" | "ETA" | "NEXT_STEP"); also reused by AI_CREATE_ACTION
    # (carries the tool-supplied action_code) and AI_SEND_SECURE_LINK (carries link_type) —
    # both are LLM-classified single-token values, the same shape ASK_QUESTION's topic is.
    topic: str | None = None
    document_type: str | None = None  # DISPUTE_DOCUMENT's disputed document
    summary: str | None = None  # DISSATISFIED / COMPLAINT_REQUEST / AI_CREATE_ACTION's reason
    # AI_SCHEDULE_CALLBACK only — a customer-proposed window is a real fact the LLM
    # extracted, not something the workflow should override with a fixed default (unlike
    # the existing CUSTOMER_DRIVING branch, which has no customer-proposed window to honor).
    callback_window_start: datetime | None = None
    callback_window_end: datetime | None = None
    # COMPLAINT_REQUEST only — the register_complaint tool's own classification; falls back
    # to the workflow's existing CLAIM_DELAY/MEDIUM defaults when absent (e.g. the fake/text
    # harness's scripted signals, which never set these), never invented by the workflow.
    complaint_category: str | None = None
    severity: Literal["LOW", "MEDIUM", "HIGH"] | None = None


class CallSessionInput(BaseModel):
    call_id: str
    customer_id: str
    claim_id: str
    call_job_id: str | None = None
    attempt_number: int = 1
    # Answer-detection stub (task 4/§0.5) — Phase 1 has no real telephony to classify an
    # answer, so the caller (a test harness, or a real vendor adapter from Phase 2/6)
    # supplies the outcome directly. "HUMAN_ANSWERED" | "NO_ANSWER" | "VOICEMAIL" | "FAILED".
    simulated_answer_result: str = "HUMAN_ANSWERED"


class CallSessionOutput(BaseModel):
    call_id: str
    disposition_code: str


class CallAttemptRead(BaseModel):
    """Dashboard/API-facing read shape for calls/router.py (Batch 15) — mirrors
    CallAttempt's spec §6.10/§23 fields. response_model, per CLAUDE.md §2.2, is what keeps
    an internal-only column from ever leaking past what this schema declares."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_id: str
    claim_id: str
    call_job_id: str | None
    attempt_number: int
    attempted_at: datetime
    answer_result: str | None
    disposition_code: str | None
    customer_reached: bool
    right_party: bool | None
    verified: bool
    verification_level: str | None
    status_delivered: str | None
    resolution: str | None
    duration_seconds: int | None
    next_attempt_at: datetime | None
    voicemail_detected: bool
    attempts_remaining: int | None


class StartCallInput(BaseModel):
    """POST /calls — an ad-hoc, single-attempt entry point (bypasses
    RetrySchedulerWorkflow's retry policy entirely; spec §27's Calls section)."""

    customer_id: str
    claim_id: str
    call_id: str | None = None
    simulated_answer_result: str = "HUMAN_ANSWERED"


class StartCallOutput(BaseModel):
    call_id: str
    workflow_id: str
