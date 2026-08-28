"""The tool-dispatch -> Temporal-signal bridge (voice/tools.py's dispatch_tool_call,
.claude/specs/phase-2-backend-spec.md §0.3/§4.4), proven against a real CallSessionWorkflow
and a real Temporal worker — the same pattern tests/integration/test_phase1_e2e.py already
established, one layer closer to the real pipeline: these tests call dispatch_tool_call(...)
directly (standing in for voice/pipeline.py's LLM-tool-use turn) instead of sending raw
customer_utterance signals, proving the bridge table itself is wired correctly without
needing a real STT/LLM/TTS adapter in the loop.
"""

from datetime import datetime, timedelta

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
from src.voice.tools import dispatch_tool_call
from src.workflow_runner import SANDBOXED_WORKFLOW_RUNNER

pytestmark = pytest.mark.integration

_TASK_QUEUE = "phase2-signal-bridge"


async def _seed_customer_and_claim(db, *, suffix: str, factor_value: str = "1990") -> dict:
    from src.claims.constants import ClaimStage
    from src.claims.models import MotorClaim, MotorPolicy
    from src.customers.models import Customer, CustomerAuthFactor

    customer_id = f"CUST-P2SB-{suffix}"
    db.add(Customer(id=customer_id, full_name="Bridge Test", phone_e164=f"+9715{suffix}"))
    await db.flush()
    db.add(
        CustomerAuthFactor(
            id=f"FACTOR-P2SB-{suffix}",
            customer_id=customer_id,
            factor_type="BIRTH_MONTH_YEAR",
            factor_value_hash=hash_factor_value(factor_value),
        )
    )
    db.add(
        MotorPolicy(
            id=f"POL-P2SB-{suffix}",
            customer_id=customer_id,
            policy_number="P1",
            vehicle_plate="X",
            vehicle_make_model="Y",
        )
    )
    await db.flush()
    claim_id = f"CLM-P2SB-{suffix}"
    db.add(
        MotorClaim(
            id=claim_id,
            policy_id=f"POL-P2SB-{suffix}",
            customer_id=customer_id,
            claim_stage=ClaimStage.REPAIR_AUTHORIZED,
            language="en",
            approved_customer_message_key="MOTOR_REPAIR_AUTHORIZED",
        )
    )
    await db.commit()
    return {"customer_id": customer_id, "claim_id": claim_id}


@pytest.fixture
async def worker(temporal_env):
    async with Worker(
        temporal_env.client,
        task_queue=_TASK_QUEUE,
        workflows=[CallSessionWorkflow, ComplaintSlaMonitorWorkflow],
        activities=[*ALL_CALLS_ACTIVITIES, *ALL_COMPLAINTS_ACTIVITIES],
        workflow_runner=SANDBOXED_WORKFLOW_RUNNER,
    ):
        yield


async def _start(temporal_env, call_id: str, seeded: dict):
    return await temporal_env.client.start_workflow(
        CallSessionWorkflow.run,
        CallSessionInput(
            call_id=call_id, customer_id=seeded["customer_id"], claim_id=seeded["claim_id"]
        ),
        id=f"call-session-{seeded['customer_id']}",
        task_queue=_TASK_QUEUE,
        execution_timeout=timedelta(seconds=60),
    )


async def _authenticate_to_follow_up(handle):
    """Drives the workflow to FOLLOW_UP — every tool this file bridges is only reachable
    once the call is authenticated and past status delivery, exactly as voice/pipeline.py's
    real turn loop would experience it."""
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="RIGHT_PARTY_CONFIRMED"),
    )
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="AUTH_ANSWER", value="1990"),
    )


async def test_schedule_callback_tool_honors_the_llm_proposed_window(
    worker, temporal_env, db_session_committed
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="CALLBACK")
    call_id = "CALL-P2SB-CALLBACK"
    handle = await _start(temporal_env, call_id, seeded)
    await _authenticate_to_follow_up(handle)

    start = datetime(2026, 9, 1, 14, 0, 0)
    end = datetime(2026, 9, 1, 16, 0, 0)
    await dispatch_tool_call(
        name="schedule_callback",
        args={
            "customer_id": seeded["customer_id"],
            "claim_id": seeded["claim_id"],
            "callback_window_start": start.isoformat(),
            "callback_window_end": end.isoformat(),
            "reason": "Customer asked for a specific time",
        },
        call_id=call_id,
        workflow_handle=handle,
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.CALLBACK_REQUESTED.value

    from src.actions.models import Callback

    row = (
        (
            await db_session_committed.execute(
                select(Callback).where(Callback.customer_id == seeded["customer_id"])
            )
        )
        .scalars()
        .one()
    )
    assert row.callback_window_start == start  # the LLM's window, not a hardcoded default
    assert row.callback_window_end == end
    assert row.reason == "Customer asked for a specific time"


async def test_create_action_tool_uses_the_llm_supplied_action_code(
    worker, temporal_env, db_session_committed
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="ACTION")
    call_id = "CALL-P2SB-ACTION"
    handle = await _start(temporal_env, call_id, seeded)
    await _authenticate_to_follow_up(handle)

    await dispatch_tool_call(
        name="create_action",
        args={
            "claim_id": seeded["claim_id"],
            "action_code": "GARAGE_CONTACT_REQUEST",
            "summary": "Customer wants the garage to call back",
        },
        call_id=call_id,
        workflow_handle=handle,
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.SUCCESS_ACTION_CREATED.value

    from src.actions.constants import ActionCode
    from src.actions.models import ClaimAction

    row = (
        (
            await db_session_committed.execute(
                select(ClaimAction).where(ClaimAction.claim_id == seeded["claim_id"])
            )
        )
        .scalars()
        .one()
    )
    assert row.action_code == ActionCode.GARAGE_CONTACT_REQUEST


async def test_create_escalation_tool_transfers_to_human(
    worker, temporal_env, db_session_committed
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="ESCALATE")
    call_id = "CALL-P2SB-ESCALATE"
    handle = await _start(temporal_env, call_id, seeded)
    await _authenticate_to_follow_up(handle)

    await dispatch_tool_call(
        name="create_escalation",
        args={"call_id": call_id, "reason": "Customer needs a claims specialist"},
        call_id=call_id,
        workflow_handle=handle,
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.SUCCESS_HUMAN_TRANSFER.value


async def test_register_complaint_tool_carries_its_own_category_and_severity(
    worker, temporal_env, db_session_committed
):
    """Proves the Batch 2 CustomerIntentSignal fix: the tool's own classification reaches
    the Complaint row, not the workflow's CLAIM_DELAY/MEDIUM fallback defaults."""
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="COMPLAINT")
    call_id = "CALL-P2SB-COMPLAINT"
    handle = await _start(temporal_env, call_id, seeded)
    await _authenticate_to_follow_up(handle)

    await dispatch_tool_call(
        name="register_complaint",
        args={
            "claim_id": seeded["claim_id"],
            "complaint_category": "REPAIR_QUALITY",
            "customer_statement_summary": "The repair work is substandard",
            "severity": "HIGH",
        },
        call_id=call_id,
        workflow_handle=handle,
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.SUCCESS_COMPLAINT_REGISTERED.value

    from src.complaints.models import Complaint

    row = (
        (
            await db_session_committed.execute(
                select(Complaint).where(Complaint.claim_id == seeded["claim_id"])
            )
        )
        .scalars()
        .one()
    )
    assert row.complaint_category == "REPAIR_QUALITY"
    assert row.severity == "HIGH"


async def test_send_secure_link_tool_creates_a_document_link_action(
    worker, temporal_env, db_session_committed
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="LINK")
    call_id = "CALL-P2SB-LINK"
    handle = await _start(temporal_env, call_id, seeded)
    await _authenticate_to_follow_up(handle)

    await dispatch_tool_call(
        name="send_secure_link",
        args={"customer_id": seeded["customer_id"], "link_type": "DOCUMENT_UPLOAD"},
        call_id=call_id,
        workflow_handle=handle,
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.SUCCESS_ACTION_CREATED.value

    from src.actions.constants import ActionCode
    from src.actions.models import ClaimAction

    row = (
        (
            await db_session_committed.execute(
                select(ClaimAction).where(ClaimAction.claim_id == seeded["claim_id"])
            )
        )
        .scalars()
        .one()
    )
    assert row.action_code == ActionCode.DOCUMENT_SUBMISSION_LINK_REQUEST


async def test_dtmf_fallback_signal_routes_to_callback(worker, temporal_env, db_session_committed):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DTMF1")
    call_id = "CALL-P2SB-DTMF1"
    handle = await _start(temporal_env, call_id, seeded)

    await handle.signal(CallSessionWorkflow.dtmf_fallback, "CALLBACK")

    result = await handle.result()
    assert result.disposition_code == DispositionCode.DTMF_FALLBACK_ACTIVATED.value

    from src.actions.models import Callback

    row = (
        (
            await db_session_committed.execute(
                select(Callback).where(Callback.customer_id == seeded["customer_id"])
            )
        )
        .scalars()
        .one()
    )
    assert row.reason == "DTMF_FALLBACK"


async def test_dtmf_fallback_signal_routes_to_human(worker, temporal_env, db_session_committed):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DTMF2")
    call_id = "CALL-P2SB-DTMF2"
    handle = await _start(temporal_env, call_id, seeded)

    await handle.signal(CallSessionWorkflow.dtmf_fallback, "HUMAN")

    result = await handle.result()
    assert result.disposition_code == DispositionCode.DTMF_FALLBACK_ACTIVATED.value

    from src.actions.models import Escalation

    row = (
        (
            await db_session_committed.execute(
                select(Escalation).where(Escalation.call_id == call_id)
            )
        )
        .scalars()
        .one()
    )
    assert row.reason == "DTMF_FALLBACK"


async def test_current_verification_level_query_reflects_real_auth_state(
    worker, temporal_env, db_session_committed
):
    """spec §36 rule 1's mechanism, proven against a real workflow (the unit test mocks the
    handle; this confirms the actual query handler behaves identically)."""
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="QUERY")
    call_id = "CALL-P2SB-QUERY"
    handle = await _start(temporal_env, call_id, seeded)

    assert await handle.query(CallSessionWorkflow.current_verification_level) == "L0"

    await _authenticate_to_follow_up(handle)
    # give the workflow a moment to process the signals before querying
    import asyncio

    for _ in range(20):
        if await handle.query(CallSessionWorkflow.current_verification_level) == "L1":
            break
        await asyncio.sleep(0.1)
    assert await handle.query(CallSessionWorkflow.current_verification_level) == "L1"

    await handle.signal(CallSessionWorkflow.call_dropped)
    await handle.result()
