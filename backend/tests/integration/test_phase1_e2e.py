"""The Phase 1 exit-criteria proof — the fake/text conversation harness driving the real
CallSessionWorkflow through a real Temporal worker for each of the 15 branches in
phases/phase-1-deterministic-core.md / spec §38's Developer Definition of Done. See
.claude/specs/phase-1-backend-spec.md §12 and decision 0.5.

Each test starts a CallSessionWorkflow, sends a scripted sequence of signals (never real
text/audio — the already-classified intent, exactly what Phase 2's real voice/pipeline.py
will extract and signal in once it exists), awaits the result, and asserts both
CallAttempt.disposition_code and the resulting AuditEvent rows — never log inspection,
matching the phase's own exit-criteria wording.

13 of 15 branches are reachable through CallSessionWorkflow alone (this file); the
remaining 2 (NO_ANSWER -> retry, CONCURRENT_CALL -> aborted) need RetrySchedulerWorkflow
and land in test_phase1_retry_scheduler_e2e.py (Batch 13/14).
"""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select
from temporalio.worker import Worker

from src.calls.activities import ALL_CALLS_ACTIVITIES
from src.calls.constants import DispositionCode
from src.calls.schemas import CallSessionInput, CustomerIntentSignal
from src.calls.workflows import CallSessionWorkflow
from src.complaints.activities import ALL_COMPLAINTS_ACTIVITIES
from src.complaints.workflows import ComplaintSlaMonitorWorkflow
from src.customers.service import hash_factor_value
from src.workflow_runner import SANDBOXED_WORKFLOW_RUNNER

pytestmark = pytest.mark.integration

_TASK_QUEUE = "phase1-e2e"


async def _seed_customer_and_claim(
    db, *, suffix: str, factor_value: str = "1990", claim_stage="REPAIR_AUTHORIZED"
) -> dict:
    from src.claims.constants import ClaimStage
    from src.claims.models import MotorClaim, MotorPolicy
    from src.customers.models import Customer, CustomerAuthFactor

    customer_id = f"CUST-E2E-{suffix}"
    db.add(Customer(id=customer_id, full_name="x", phone_e164=f"+9715{suffix}"))
    await db.flush()
    db.add(
        CustomerAuthFactor(
            id=f"FACTOR-E2E-{suffix}",
            customer_id=customer_id,
            factor_type="BIRTH_MONTH_YEAR",
            factor_value_hash=hash_factor_value(factor_value),
        )
    )
    db.add(
        MotorPolicy(
            id=f"POL-E2E-{suffix}",
            customer_id=customer_id,
            policy_number="P1",
            vehicle_plate="X",
            vehicle_make_model="Y",
        )
    )
    await db.flush()
    claim_id = f"CLM-E2E-{suffix}"
    db.add(
        MotorClaim(
            id=claim_id,
            policy_id=f"POL-E2E-{suffix}",
            customer_id=customer_id,
            claim_stage=ClaimStage(claim_stage),
            language="en",
            approved_customer_message_key=f"MOTOR_{claim_stage}",
        )
    )
    await db.commit()
    return {"customer_id": customer_id, "claim_id": claim_id}


@pytest.fixture
async def worker(temporal_env):
    # ComplaintSlaMonitorWorkflow is registered here too — CallSessionWorkflow's
    # COMPLAINT_REQUEST branch starts it as an ABANDON-policy child, and an unregistered
    # child workflow type would otherwise sit forever unexecuted on the shared Temporal
    # server rather than actually running to completion.
    async with Worker(
        temporal_env.client,
        task_queue=_TASK_QUEUE,
        workflows=[CallSessionWorkflow, ComplaintSlaMonitorWorkflow],
        activities=[*ALL_CALLS_ACTIVITIES, *ALL_COMPLAINTS_ACTIVITIES],
        workflow_runner=SANDBOXED_WORKFLOW_RUNNER,
    ):
        yield


async def _start(temporal_env, call_id: str, seeded: dict, **input_overrides):
    handle = await temporal_env.client.start_workflow(
        CallSessionWorkflow.run,
        CallSessionInput(
            call_id=call_id,
            customer_id=seeded["customer_id"],
            claim_id=seeded["claim_id"],
            **input_overrides,
        ),
        id=f"call-session-{seeded['customer_id']}",
        task_queue=_TASK_QUEUE,
        execution_timeout=timedelta(seconds=60),
    )
    return handle


async def _audit_rows(db, call_id: str):
    from src.audit.models import AuditEvent

    result = await db.execute(select(AuditEvent).where(AuditEvent.call_id == call_id))
    return result.scalars().all()


async def _call_attempt(db, call_id: str):
    from src.calls.models import CallAttempt

    return await db.get(CallAttempt, call_id)


# --- 5/15 + 15/15: NORMAL CUSTOMER -> status delivered / SUCCESS -> summary -------------


async def test_normal_customer_status_delivered(worker, temporal_env, db_session_committed):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="NORMAL")
    call_id = "CALL-E2E-NORMAL"
    handle = await _start(temporal_env, call_id, seeded)

    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="RIGHT_PARTY_CONFIRMED"),
    )
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="AUTH_ANSWER", value="1990"),
    )
    await handle.signal(
        CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="NOTHING_ELSE")
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.SUCCESS_STATUS_DELIVERED.value

    attempt = await _call_attempt(db_session_committed, call_id)
    assert attempt.verified is True
    assert attempt.verification_level == "L1"
    assert attempt.status_delivered == "MOTOR_REPAIR_AUTHORIZED"

    audit_rows = await _audit_rows(db_session_committed, call_id)
    assert any(
        row.action_taken == DispositionCode.SUCCESS_STATUS_DELIVERED.value for row in audit_rows
    )


async def _authenticate(handle):
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="RIGHT_PARTY_CONFIRMED"),
    )
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="AUTH_ANSWER", value="1990"),
    )


# --- 6/15: QUESTION -> grounded answer --------------------------------------------------


async def test_question_resolved(worker, temporal_env, db_session_committed):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="QUESTION")
    call_id = "CALL-E2E-QUESTION"
    handle = await _start(temporal_env, call_id, seeded)

    await _authenticate(handle)
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="ASK_QUESTION", topic="GARAGE"),
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.SUCCESS_STATUS_AND_QUERY_RESOLVED.value


# --- 7/15: DISPUTE -> action created -----------------------------------------------------


async def test_dispute_creates_action(worker, temporal_env, db_session_committed):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DISPUTE")
    call_id = "CALL-E2E-DISPUTE"
    handle = await _start(temporal_env, call_id, seeded)

    await _authenticate(handle)
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="DISPUTE_DOCUMENT", document_type="POLICE_REPORT"),
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.SUCCESS_ACTION_CREATED.value

    from src.actions.constants import ActionCode
    from src.actions.models import ClaimAction

    rows = (
        (
            await db_session_committed.execute(
                select(ClaimAction).where(ClaimAction.claim_id == seeded["claim_id"])
            )
        )
        .scalars()
        .all()
    )
    assert any(r.action_code == ActionCode.DOCUMENT_STATUS_DISPUTE for r in rows)


# --- 8/15: DISSATISFACTION -> escalation (action) -----------------------------------------


async def test_dissatisfaction_creates_escalation_action(
    worker, temporal_env, db_session_committed
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DISSAT")
    call_id = "CALL-E2E-DISSAT"
    handle = await _start(temporal_env, call_id, seeded)

    await _authenticate(handle)
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(
            intent="DISSATISFIED", summary="This is ridiculous, two weeks waiting"
        ),
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.SUCCESS_ACTION_CREATED.value


# --- 9/15: COMPLAINT -> complaint created --------------------------------------------------


async def test_complaint_request_creates_complaint(worker, temporal_env, db_session_committed):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="COMPLAINT")
    call_id = "CALL-E2E-COMPLAINT"
    handle = await _start(temporal_env, call_id, seeded)

    await _authenticate(handle)
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="COMPLAINT_REQUEST", summary="Formal complaint about delay"),
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.SUCCESS_COMPLAINT_REGISTERED.value

    from src.complaints.models import Complaint

    rows = (
        (
            await db_session_committed.execute(
                select(Complaint).where(Complaint.claim_id == seeded["claim_id"])
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].acknowledgment_due_at is not None
    assert rows[0].resolution_due_at is not None


# --- 10/15: HUMAN REQUEST -> transfer/callback ----------------------------------------------


async def test_human_request_before_authentication(worker, temporal_env, db_session_committed):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="HUMAN1")
    call_id = "CALL-E2E-HUMAN1"
    handle = await _start(temporal_env, call_id, seeded)

    await handle.signal(
        CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="RIGHT_PARTY_CONFIRMED")
    )
    await handle.signal(CallSessionWorkflow.human_request_detected)

    result = await handle.result()
    assert result.disposition_code == DispositionCode.SUCCESS_HUMAN_TRANSFER.value

    from src.actions.models import Escalation

    rows = (
        (
            await db_session_committed.execute(
                select(Escalation).where(Escalation.call_id == call_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].reason == "CUSTOMER_REQUESTED_HUMAN"


async def test_human_request_after_status_delivered(worker, temporal_env, db_session_committed):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="HUMAN2")
    call_id = "CALL-E2E-HUMAN2"
    handle = await _start(temporal_env, call_id, seeded)

    await _authenticate(handle)
    await handle.signal(CallSessionWorkflow.human_request_detected)

    result = await handle.result()
    assert result.disposition_code == DispositionCode.SUCCESS_HUMAN_TRANSFER.value


# --- 11/15: BACKEND FAILURE -> deterministic recovery ---------------------------------------


async def test_backend_failure_during_status_delivery(
    worker, temporal_env, db_session_committed, monkeypatch
):
    """A real claim IS seeded (CallAttempt.claim_id is a real FK — it must exist) — the
    backend failure is instead simulated by making claims/service.py::get_claim raise, so
    deliver_status fails on every retry and the workflow's ActivityError catch around it
    fires, exercising the same path a genuine DB/network outage would. The activity-level
    with_runtime_recovery/RuntimeFailureEvent recording itself is already covered in
    isolation by tests/unit/test_calls_activities.py — this test is about the WORKFLOW's
    reaction (spec §14 Type E), not re-proving the activity wrapper.
    """
    import src.claims.service as claims_service_module

    async def _broken_get_claim(session, claim_id):
        raise RuntimeError("simulated backend outage")

    monkeypatch.setattr(claims_service_module, "get_claim", _broken_get_claim)

    seeded = await _seed_customer_and_claim(db_session_committed, suffix="BACKEND")
    call_id = "CALL-E2E-BACKEND"
    handle = await _start(temporal_env, call_id, seeded)
    await _authenticate(handle)

    result = await handle.result()
    assert result.disposition_code == DispositionCode.BACKEND_SYSTEM_FAILURE.value

    from src.actions.constants import ActionCode
    from src.actions.models import ClaimAction

    rows = (
        (
            await db_session_committed.execute(
                select(ClaimAction).where(ClaimAction.claim_id == seeded["claim_id"])
            )
        )
        .scalars()
        .all()
    )
    assert any(r.action_code == ActionCode.BACKEND_DATA_VERIFICATION_REQUEST for r in rows)


# --- 12/15: OTP LIMIT -> lockout ------------------------------------------------------------


async def test_otp_limit_lockout(worker, temporal_env, db_session_committed):
    from src.verification.config import VerificationConfig

    seeded = await _seed_customer_and_claim(db_session_committed, suffix="OTP")
    call_id = "CALL-E2E-OTP"
    handle = await _start(temporal_env, call_id, seeded)

    await handle.signal(
        CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="RIGHT_PARTY_CONFIRMED")
    )
    await handle.signal(
        CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="REQUEST_OTP")
    )

    max_attempts = VerificationConfig(_env_file=None).MAX_OTP_ATTEMPTS
    for _ in range(max_attempts):
        await handle.signal(
            CallSessionWorkflow.customer_utterance,
            CustomerIntentSignal(intent="OTP_ANSWER", value="000000"),
        )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.OTP_LOCKED.value


# --- 13/15: CALL DROP -> auth expires --------------------------------------------------------


async def test_call_dropped_pre_auth(worker, temporal_env, db_session_committed):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DROP1")
    call_id = "CALL-E2E-DROP1"
    handle = await _start(temporal_env, call_id, seeded)

    await handle.signal(
        CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="RIGHT_PARTY_CONFIRMED")
    )
    await handle.signal(CallSessionWorkflow.call_dropped)

    result = await handle.result()
    assert result.disposition_code == DispositionCode.CALL_DROPPED_PRE_AUTH.value


async def test_call_dropped_post_auth(worker, temporal_env, db_session_committed):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DROP2")
    call_id = "CALL-E2E-DROP2"
    handle = await _start(temporal_env, call_id, seeded)

    await _authenticate(handle)
    await handle.signal(CallSessionWorkflow.call_dropped)

    result = await handle.result()
    assert result.disposition_code == DispositionCode.CALL_DROPPED_POST_AUTH.value


# --- 3/15: WRONG PERSON -> privacy-safe termination ------------------------------------------


async def test_wrong_party(worker, temporal_env, db_session_committed):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="WRONG")
    call_id = "CALL-E2E-WRONG"
    handle = await _start(temporal_env, call_id, seeded)

    await handle.signal(
        CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="WRONG_PARTY")
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.WRONG_PARTY.value


# --- 4/15: AUTH FAILURE -> disclosure blocked -------------------------------------------------


async def test_auth_failure(worker, temporal_env, db_session_committed):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="AUTHFAIL")
    call_id = "CALL-E2E-AUTHFAIL"
    handle = await _start(temporal_env, call_id, seeded)

    await handle.signal(
        CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="RIGHT_PARTY_CONFIRMED")
    )
    for _ in range(2):  # MAX_AUTH_ATTEMPTS
        await handle.signal(
            CallSessionWorkflow.customer_utterance,
            CustomerIntentSignal(intent="AUTH_ANSWER", value="wrong-answer"),
        )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.AUTH_FAILED.value

    attempt = await _call_attempt(db_session_committed, call_id)
    assert attempt.verified is False


# --- 2/15: BUSY CUSTOMER -> callback -----------------------------------------------------------


async def test_busy_customer_creates_callback(worker, temporal_env, db_session_committed):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="BUSY")
    call_id = "CALL-E2E-BUSY"
    handle = await _start(temporal_env, call_id, seeded)

    await handle.signal(
        CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="CUSTOMER_DRIVING")
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.CALLBACK_REQUESTED.value

    from src.actions.models import Callback

    rows = (
        (
            await db_session_committed.execute(
                select(Callback).where(Callback.customer_id == seeded["customer_id"])
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].reason == "CUSTOMER_DRIVING"


# --- risk mitigation: signal races (Batch 11 risk #2) --------------------------------------


async def test_signal_racing_a_concurrent_call_drop_is_not_silently_dropped(
    worker, temporal_env, db_session_committed
):
    """Sends a RIGHT_PARTY_CONFIRMED customer_utterance concurrently with call_dropped
    (asyncio.gather — no await between them on the client side), rather than sequentially.
    A single-slot `_pending_signals` design (instead of the list this workflow actually
    uses) could let `call_dropped`'s flag-only signal arrive and be "noticed" by
    `_wait_for_signal` while the utterance signal it raced against gets silently discarded
    before the right-party-check stage ever reads it. Asserting `right_party is True` on
    the finalized CallAttempt proves the queued utterance was processed — not dropped —
    even though the call ends via CALL_DROPPED_PRE_AUTH shortly after, at the very next
    wait point (authentication), which is the correct place for a drop noticed only after
    right-party check to take effect (spec §10.6.3: authentication authority is bound to
    the live call session).
    """
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="RACE")
    call_id = "CALL-E2E-RACE"
    handle = await _start(temporal_env, call_id, seeded)

    await asyncio.gather(
        handle.signal(
            CallSessionWorkflow.customer_utterance,
            CustomerIntentSignal(intent="RIGHT_PARTY_CONFIRMED"),
        ),
        handle.signal(CallSessionWorkflow.call_dropped),
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.CALL_DROPPED_PRE_AUTH.value

    attempt = await _call_attempt(db_session_committed, call_id)
    assert attempt.right_party is True


# --- risk mitigation: idempotency-key sequencing under concurrency (Batch 11 risk #1) -------


async def test_concurrent_workflows_never_collide_on_idempotency_key(
    worker, temporal_env, db_session_committed
):
    """Two different CallSessionWorkflow runs (different customers, so no distributed-lock
    conflict) each mint their own `{call_id}-ACTION-N` idempotency keys from workflow-local
    state incremented only inside the main coroutine — running them concurrently must never
    collide on the idempotency_record primary key."""
    seeded_a = await _seed_customer_and_claim(db_session_committed, suffix="CONC-A")
    seeded_b = await _seed_customer_and_claim(db_session_committed, suffix="CONC-B")

    handle_a = await _start(temporal_env, "CALL-E2E-CONC-A", seeded_a)
    handle_b = await _start(temporal_env, "CALL-E2E-CONC-B", seeded_b)

    async def _drive_to_dispute(handle):
        await handle.signal(
            CallSessionWorkflow.customer_utterance,
            CustomerIntentSignal(intent="RIGHT_PARTY_CONFIRMED"),
        )
        await handle.signal(
            CallSessionWorkflow.customer_utterance,
            CustomerIntentSignal(intent="AUTH_ANSWER", value="1990"),
        )
        await handle.signal(
            CallSessionWorkflow.customer_utterance,
            CustomerIntentSignal(intent="DISPUTE_DOCUMENT", document_type="POLICE_REPORT"),
        )

    await asyncio.gather(_drive_to_dispute(handle_a), _drive_to_dispute(handle_b))
    results = await asyncio.gather(handle_a.result(), handle_b.result())

    assert all(r.disposition_code == DispositionCode.SUCCESS_ACTION_CREATED.value for r in results)

    from src.idempotency import IdempotencyRecord

    rows = (
        (
            await db_session_committed.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.idempotency_key.in_(
                        ["CALL-E2E-CONC-A-ACTION-1", "CALL-E2E-CONC-B-ACTION-1"]
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2  # both committed distinctly — no PK collision, no lost write
