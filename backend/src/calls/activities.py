"""Real activities for CallSessionWorkflow (Batch 11 wires these in) — task 5/6/7/10.
Every activity opens its own session via get_session_factory() rather than
Depends(get_db()), since activities never run inside a FastAPI request, matching
record_audit_event's existing Phase 0 pattern.

with_runtime_recovery() is the one shared wrapper implementing spec §10.6.1/§14 Type E:
a dependency call that times out gets recorded as a RuntimeFailureEvent and re-raised —
Temporal's own activity RetryPolicy (configured at the workflow's execute_activity call
site, not here) governs retries; exhausting it surfaces as an ActivityError the workflow
catches and maps to BACKEND_SYSTEM_FAILURE (spec §36 rule 26: never improvise past this).
"""

import asyncio
import functools
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel
from temporalio import activity

from src.actions import service as actions_service
from src.audit import service as audit_service
from src.calls import service as calls_service
from src.calls.constants import CallState
from src.claims import service as claims_service
from src.claims.schemas import ClaimStatusRead
from src.complaints import service as complaints_service
from src.complaints.config import ComplaintsConfig
from src.config import settings
from src.database import get_session_factory
from src.verification import service as verification_service
from src.verification.adapters.otp_delivery import get_otp_delivery_adapter
from src.verification.config import VerificationConfig


class RecordAuditEventInput(BaseModel):
    decision: str
    reason_code: str
    policy_rule: str | None = None
    action_taken: str | None = None
    call_id: str | None = None
    correlation_id: str | None = None
    actor: Literal["SYSTEM", "AI", "HUMAN"] = "SYSTEM"
    metadata: dict[str, Any] | None = None


@activity.defn(name="record_audit_event")
async def record_audit_event(inp: RecordAuditEventInput) -> str:
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        event = await audit_service.record_event(
            session,
            decision=inp.decision,
            reason_code=inp.reason_code,
            policy_rule=inp.policy_rule,
            action_taken=inp.action_taken,
            call_id=inp.call_id,
            correlation_id=inp.correlation_id,
            actor=inp.actor,
            metadata=inp.metadata,
        )
        event_id = event.id
    return event_id


# --- runtime recovery ------------------------------------------------------------------


async def _record_runtime_failure(
    *, call_id: str | None, component: str, failure_type: str, recovery_action: str
) -> None:
    from src.audit.models import RuntimeFailureEvent

    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        session.add(
            RuntimeFailureEvent(
                call_id=call_id,
                component=component,
                failure_type=failure_type,
                recovery_action=recovery_action,
            )
        )


def with_runtime_recovery(*, component: str, failure_type: str):
    """Decorator for an activity function whose first positional/keyword argument is a
    Pydantic input model carrying an optional `call_id` field — wraps the call with
    settings.BACKEND_SOFT_WAIT_MS as a soft timeout. On timeout, records a
    RuntimeFailureEvent (recovery_action="SAFE_TERMINATION" — the caller decides what
    actually happens next) and re-raises so Temporal's RetryPolicy/failure surface handles
    it, per spec §10.6.1.
    """

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(inp, *args, **kwargs):
            try:
                return await asyncio.wait_for(
                    fn(inp, *args, **kwargs), timeout=settings.BACKEND_SOFT_WAIT_MS / 1000
                )
            except TimeoutError:
                await _record_runtime_failure(
                    call_id=getattr(inp, "call_id", None),
                    component=component,
                    failure_type=failure_type,
                    recovery_action="SAFE_TERMINATION",
                )
                raise

        return wrapper

    return decorator


# --- call attempt / session lifecycle ---------------------------------------------------


class CreateCallAttemptInput(BaseModel):
    call_id: str
    customer_id: str
    claim_id: str
    call_job_id: str | None
    attempt_number: int
    attempted_at: datetime


@activity.defn(name="create_call_attempt")
async def create_call_attempt(inp: CreateCallAttemptInput) -> str:
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        attempt = await calls_service.create_call_attempt(
            session,
            call_id=inp.call_id,
            customer_id=inp.customer_id,
            claim_id=inp.claim_id,
            call_job_id=inp.call_job_id,
            attempt_number=inp.attempt_number,
            attempted_at=inp.attempted_at,
        )
        return attempt.id


class ClassifyAnswerInput(BaseModel):
    call_id: str
    simulated_answer_result: str


@activity.defn(name="classify_answer")
async def classify_answer(inp: ClassifyAnswerInput) -> str:
    """Answer-detection stub — spec §5, task 4. Phase 1 has no real telephony to classify
    an answer with, so this activity simply returns the caller-supplied simulated result.
    A real telephony vendor adapter (Phase 2/6) replaces this activity's body only — the
    workflow-side contract (a str answer_result) does not change."""
    return inp.simulated_answer_result


class CreateCallSessionInput(BaseModel):
    call_attempt_id: str
    state: CallState


@activity.defn(name="create_call_session")
async def create_call_session(inp: CreateCallSessionInput) -> str:
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        call_session = await calls_service.create_call_session(
            session, call_attempt_id=inp.call_attempt_id, state=inp.state
        )
        return call_session.id


class UpdateCallSessionInput(BaseModel):
    call_session_id: str
    state: CallState | None = None
    right_party_confirmed: bool | None = None
    verification_level: str | None = None
    status_already_disclosed: bool | None = None
    pending_action: str | None = None


@activity.defn(name="update_call_session")
async def update_call_session(inp: UpdateCallSessionInput) -> None:
    from src.calls.models import CallSession

    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        call_session = await session.get(CallSession, inp.call_session_id)
        assert call_session is not None, f"no CallSession row for {inp.call_session_id}"
        if inp.state is not None:
            call_session.state = inp.state
        if inp.right_party_confirmed is not None:
            call_session.right_party_confirmed = inp.right_party_confirmed
        if inp.verification_level is not None:
            call_session.verification_level = inp.verification_level
        if inp.status_already_disclosed is not None:
            call_session.status_already_disclosed = inp.status_already_disclosed
        if inp.pending_action is not None:
            call_session.pending_action = inp.pending_action


class FinalizeOutcomeInput(BaseModel):
    call_attempt_id: str
    disposition_code: str
    answer_result: str | None = None
    customer_reached: bool = False
    right_party: bool | None = None
    verified: bool = False
    verification_level: str | None = None
    status_delivered: str | None = None
    resolution: str | None = None
    duration_seconds: int | None = None
    next_attempt_at: datetime | None = None
    voicemail_detected: bool = False
    attempts_remaining: int | None = None


@activity.defn(name="finalize_outcome")
async def finalize_outcome(inp: FinalizeOutcomeInput) -> None:
    from src.calls.constants import DispositionCode

    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        await calls_service.finalize_outcome(
            session,
            call_attempt_id=inp.call_attempt_id,
            disposition_code=DispositionCode(inp.disposition_code),
            answer_result=inp.answer_result,
            customer_reached=inp.customer_reached,
            right_party=inp.right_party,
            verified=inp.verified,
            verification_level=inp.verification_level,
            status_delivered=inp.status_delivered,
            resolution=inp.resolution,
            duration_seconds=inp.duration_seconds,
            next_attempt_at=inp.next_attempt_at,
            voicemail_detected=inp.voicemail_detected,
            attempts_remaining=inp.attempts_remaining,
        )


# --- authentication ----------------------------------------------------------------------


class VerifyLevel1Input(BaseModel):
    call_id: str | None = None
    call_session_id: str
    customer_id: str
    factor_type: str
    supplied_value: str
    now: datetime


class VerifyLevel1Output(BaseModel):
    outcome: str
    attempts_so_far: int


@activity.defn(name="verify_level1")
async def verify_level1(inp: VerifyLevel1Input) -> VerifyLevel1Output:
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        attempt = await verification_service.verify_level1(
            session,
            call_session_id=inp.call_session_id,
            customer_id=inp.customer_id,
            factor_type=inp.factor_type,
            supplied_value=inp.supplied_value,
            now=inp.now,
        )
        attempts_so_far = await verification_service.count_level1_attempts(
            session, inp.call_session_id
        )
        return VerifyLevel1Output(outcome=attempt.outcome, attempts_so_far=attempts_so_far)


class SendOtpInput(BaseModel):
    call_id: str | None = None
    call_session_id: str
    phone_e164: str
    now: datetime


class SendOtpOutput(BaseModel):
    challenge_id: str
    sent_count: int


@activity.defn(name="send_otp")
async def send_otp(inp: SendOtpInput) -> SendOtpOutput:
    config = VerificationConfig()
    adapter = get_otp_delivery_adapter(config.OTP_DELIVERY_PROVIDER)
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        challenge = await verification_service.send_otp(
            session,
            call_session_id=inp.call_session_id,
            phone_e164=inp.phone_e164,
            now=inp.now,
            config=config,
            adapter=adapter,
        )
        return SendOtpOutput(challenge_id=challenge.id, sent_count=challenge.sent_count)


class VerifyOtpInput(BaseModel):
    call_id: str | None = None
    challenge_id: str
    supplied_code: str
    now: datetime


class VerifyOtpOutput(BaseModel):
    status: str
    attempt_count: int


@activity.defn(name="verify_otp")
async def verify_otp(inp: VerifyOtpInput) -> VerifyOtpOutput:
    config = VerificationConfig()
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        challenge = await verification_service.verify_otp(
            session,
            challenge_id=inp.challenge_id,
            supplied_code=inp.supplied_code,
            now=inp.now,
            config=config,
        )
        return VerifyOtpOutput(status=challenge.status, attempt_count=challenge.attempt_count)


class GetAuthFactorTypeInput(BaseModel):
    customer_id: str


@activity.defn(name="get_configured_auth_factor_type")
async def get_configured_auth_factor_type(inp: GetAuthFactorTypeInput) -> str | None:
    """Level 1 needs to know WHICH factor a customer has on file before it can ask for it
    — the harness/real conversation asks the question this returns the answer to."""
    from sqlalchemy import select

    from src.customers.models import CustomerAuthFactor

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(CustomerAuthFactor).where(CustomerAuthFactor.customer_id == inp.customer_id)
        )
        row = result.scalars().first()
        return row.factor_type if row is not None else None


class GetCustomerPhoneInput(BaseModel):
    customer_id: str


@activity.defn(name="get_customer_phone")
async def get_customer_phone(inp: GetCustomerPhoneInput) -> str:
    """Level 2 (OTP) needs the registered number to send the code to (spec §10.3)."""
    from src.customers.models import Customer

    session_factory = get_session_factory()
    async with session_factory() as session:
        customer = await session.get(Customer, inp.customer_id)
        assert customer is not None, f"no Customer row for {inp.customer_id}"
        return customer.phone_e164


# --- status delivery -----------------------------------------------------------------


class DeliverStatusInput(BaseModel):
    call_id: str | None = None
    claim_id: str
    verification_level: str


@activity.defn(name="deliver_status")
@with_runtime_recovery(component="BACKEND", failure_type="BACKEND_TIMEOUT")
async def deliver_status(inp: DeliverStatusInput) -> ClaimStatusRead | None:
    from src.verification.constants import VerificationLevel

    session_factory = get_session_factory()
    async with session_factory() as session:
        claim = await claims_service.get_claim(session, inp.claim_id)
        if claim is None:
            return None
        return claims_service.get_disclosable_status(
            claim, VerificationLevel(inp.verification_level)
        )


# --- action / escalation / callback / complaint dispatch -------------------------------


class CreateActionInput(BaseModel):
    key: str
    correlation_id: str
    claim_id: str
    action_code: str
    summary: str
    source_call_id: str | None = None


@activity.defn(name="create_action")
async def create_action(inp: CreateActionInput) -> dict[str, Any]:
    from src.actions.constants import ActionCode

    session_factory = get_session_factory()
    async with session_factory() as session:
        return await actions_service.create_action(
            session,
            key=inp.key,
            correlation_id=inp.correlation_id,
            claim_id=inp.claim_id,
            action_code=ActionCode(inp.action_code),
            summary=inp.summary,
            source_call_id=inp.source_call_id,
        )


class CreateEscalationInput(BaseModel):
    key: str
    correlation_id: str
    call_id: str
    reason: str
    context_snapshot: dict[str, Any]


@activity.defn(name="create_escalation")
async def create_escalation(inp: CreateEscalationInput) -> dict[str, Any]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        return await actions_service.create_escalation(
            session,
            key=inp.key,
            correlation_id=inp.correlation_id,
            call_id=inp.call_id,
            reason=inp.reason,
            context_snapshot=inp.context_snapshot,
        )


class ScheduleCallbackInput(BaseModel):
    key: str
    correlation_id: str
    customer_id: str
    callback_window_start: datetime
    callback_window_end: datetime
    reason: str
    claim_id: str | None = None


@activity.defn(name="schedule_callback")
async def schedule_callback(inp: ScheduleCallbackInput) -> dict[str, Any]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        return await actions_service.schedule_callback(
            session,
            key=inp.key,
            correlation_id=inp.correlation_id,
            customer_id=inp.customer_id,
            claim_id=inp.claim_id,
            callback_window_start=inp.callback_window_start,
            callback_window_end=inp.callback_window_end,
            reason=inp.reason,
        )


class SendSecureLinkInput(BaseModel):
    key: str
    correlation_id: str
    claim_id: str
    customer_id: str
    link_type: str
    source_call_id: str | None = None


@activity.defn(name="send_secure_link")
async def send_secure_link(inp: SendSecureLinkInput) -> dict[str, Any]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        return await actions_service.send_secure_link(
            session,
            key=inp.key,
            correlation_id=inp.correlation_id,
            claim_id=inp.claim_id,
            customer_id=inp.customer_id,
            link_type=inp.link_type,
            source_call_id=inp.source_call_id,
        )


class CreateComplaintInput(BaseModel):
    key: str
    correlation_id: str
    claim_id: str
    source_call_id: str
    complaint_category: str
    customer_statement_summary: str
    severity: str
    preferred_contact_method: str
    now: datetime
    customer_expected_resolution: str | None = None


@activity.defn(name="create_complaint")
async def create_complaint(inp: CreateComplaintInput) -> dict[str, Any]:
    """DB write only — starting ComplaintSlaMonitorWorkflow (spec §18.1) is the calling
    WORKFLOW's job (CallSessionWorkflow's COMPLAINT_REQUEST branch, as an ABANDON-policy
    child), not this activity's. An activity independently connecting a fresh Temporal
    client here would risk pointing at the wrong server under a time-skipping test
    environment (which starts its own ephemeral server, not settings.TEMPORAL_HOST) and
    would reconnect on every single call — the workflow already runs inside the correct
    environment and can start a child workflow directly."""
    config = ComplaintsConfig()
    session_factory = get_session_factory()
    async with session_factory() as session:
        return await complaints_service.create_complaint(
            session,
            key=inp.key,
            correlation_id=inp.correlation_id,
            claim_id=inp.claim_id,
            source_call_id=inp.source_call_id,
            complaint_category=inp.complaint_category,
            customer_statement_summary=inp.customer_statement_summary,
            severity=inp.severity,
            preferred_contact_method=inp.preferred_contact_method,
            now=inp.now,
            config=config,
            customer_expected_resolution=inp.customer_expected_resolution,
        )


ALL_CALLS_ACTIVITIES = [
    record_audit_event,
    create_call_attempt,
    classify_answer,
    create_call_session,
    update_call_session,
    finalize_outcome,
    verify_level1,
    send_otp,
    verify_otp,
    get_configured_auth_factor_type,
    get_customer_phone,
    deliver_status,
    create_action,
    create_escalation,
    schedule_callback,
    create_complaint,
    send_secure_link,
]
