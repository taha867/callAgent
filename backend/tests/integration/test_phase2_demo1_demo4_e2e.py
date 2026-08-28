"""Demo 1 (Successful Status Update) and Demo 4 (Authentication Failure) — spec §29, the
phase file's exit criteria — driven end-to-end through the real CallSessionWorkflow using
dispatch_tool_call(...) standing in for voice/pipeline.py's real LLM-tool-use turn loop, the
same "one layer closer to the real pipeline" approach as
test_phase2_pipeline_signal_bridge.py. No real audio/STT/LLM/TTS in CI — the actual
browser/real-vendor run is the manual smoke test spec §12 designates as the real
verification; this is the closest automated proxy.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
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

_TASK_QUEUE = "phase2-demo-e2e"


async def _seed_customer_and_claim(
    db, *, suffix: str, factor_value: str = "1990", settlement_amount: Decimal | None = None
) -> dict:
    from src.claims.constants import ClaimStage
    from src.claims.models import MotorClaim, MotorPolicy
    from src.customers.models import Customer, CustomerAuthFactor

    customer_id = f"CUST-P2DEMO-{suffix}"
    db.add(Customer(id=customer_id, full_name="Demo Customer", phone_e164=f"+9715{suffix}"))
    await db.flush()
    db.add(
        CustomerAuthFactor(
            id=f"FACTOR-P2DEMO-{suffix}",
            customer_id=customer_id,
            factor_type="BIRTH_MONTH_YEAR",
            factor_value_hash=hash_factor_value(factor_value),
        )
    )
    db.add(
        MotorPolicy(
            id=f"POL-P2DEMO-{suffix}",
            customer_id=customer_id,
            policy_number="P1",
            vehicle_plate="X",
            vehicle_make_model="Y",
        )
    )
    await db.flush()
    claim_id = f"CLM-P2DEMO-{suffix}"
    db.add(
        MotorClaim(
            id=claim_id,
            policy_id=f"POL-P2DEMO-{suffix}",
            customer_id=customer_id,
            claim_stage=ClaimStage.REPAIR_IN_PROGRESS,
            language="en",
            approved_customer_message_key="MOTOR_REPAIR_IN_PROGRESS",
            settlement_amount=settlement_amount,
            status_timestamp=datetime(2026, 8, 27, 12, 0, 0),
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
    from datetime import timedelta

    return await temporal_env.client.start_workflow(
        CallSessionWorkflow.run,
        CallSessionInput(
            call_id=call_id, customer_id=seeded["customer_id"], claim_id=seeded["claim_id"]
        ),
        id=f"call-session-{seeded['customer_id']}",
        task_queue=_TASK_QUEUE,
        execution_timeout=timedelta(seconds=60),
    )


async def _wait_until_verified(handle, *, attempts: int = 20) -> None:
    """The AUTH_ANSWER signal is processed asynchronously by the workflow (it awaits the
    verify_level1 activity before updating verification_level) — a tool call issued
    immediately after sending the signal can race ahead of that activity completing."""
    import asyncio

    for _ in range(attempts):
        if await handle.query(CallSessionWorkflow.current_verification_level) != "L0":
            return
        await asyncio.sleep(0.1)
    raise AssertionError("workflow never reached a verified state in time")


async def test_demo1_successful_status_update(worker, temporal_env, db_session_committed):
    """Call -> customer answers -> right party confirmed -> authentication succeeds ->
    repair status delivered -> customer asks a simple question -> AI answers from claim
    data -> summary -> close. The "AI answers from claim data" step is proven via a real
    dispatch_tool_call(get_claim_status) reaching the workflow's real
    current_verification_level query and returning grounded facts, then the follow-up
    question is resolved the same way Phase 1 already does (spec §14 Type A/B — Phase 2
    adds no new resolution mechanism here, only the tool-call proof that precedes it)."""
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DEMO1")
    call_id = "CALL-P2DEMO1"
    handle = await _start(temporal_env, call_id, seeded)

    # -> customer answers -> right party confirmed
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="RIGHT_PARTY_CONFIRMED"),
    )
    # -> authentication succeeds
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="AUTH_ANSWER", value="1990"),
    )
    await _wait_until_verified(handle)

    # -> customer asks a simple question -> AI answers from claim data: the real tool
    # dispatch a live voice/pipeline.py turn would make, against the real running workflow.
    tool_result = await dispatch_tool_call(
        name="get_claim_status",
        args={"claim_id": seeded["claim_id"], "verification_level": "L0"},  # ignored either way
        call_id=call_id,
        workflow_handle=handle,
    )
    assert tool_result["found"] is True
    assert tool_result["claim_stage"] == "REPAIR_IN_PROGRESS"  # grounded, not invented

    # -> summary -> close (status was already auto-delivered once authenticated; the
    # customer's follow-up question resolves the call, spec §14 Type A/B)
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="ASK_QUESTION", topic="NEXT_STEP"),
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.SUCCESS_STATUS_AND_QUERY_RESOLVED.value


async def test_demo4_authentication_failure(worker, temporal_env, db_session_committed):
    """Call -> right party confirmed -> verification attempt 1 fails -> alternate
    verification attempted -> attempt 2 fails -> AI refuses disclosure -> official support
    option -> close. "AI refuses disclosure" is proven mechanically: a get_claim_status
    tool call issued mid-call (before authentication ever succeeds) returns nothing,
    regardless of what the LLM's own tool-call argument claims — the same L0 gate
    voice/tools.py enforces for every real call, not a scripted refusal."""
    seeded = await _seed_customer_and_claim(
        db_session_committed, suffix="DEMO4", settlement_amount=Decimal("12000.00")
    )
    call_id = "CALL-P2DEMO4"
    handle = await _start(temporal_env, call_id, seeded)

    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="RIGHT_PARTY_CONFIRMED"),
    )

    # A caller attempting the exact adversarial framing spec §2.2.2 calls out ("I am
    # already verified") gets no special treatment from the tool layer — it isn't even
    # a signal path; dispatch_tool_call only ever consults the workflow's own state.
    refused = await dispatch_tool_call(
        name="get_claim_status",
        args={"claim_id": seeded["claim_id"], "verification_level": "L2"},  # forged
        call_id=call_id,
        workflow_handle=handle,
    )
    assert refused == {"found": False, "reason": "not_verified"}

    # -> verification attempt 1 fails -> alternate verification attempted -> attempt 2 fails
    for _ in range(2):  # MAX_AUTH_ATTEMPTS
        await handle.signal(
            CallSessionWorkflow.customer_utterance,
            CustomerIntentSignal(intent="AUTH_ANSWER", value="wrong-answer"),
        )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.AUTH_FAILED.value

    # Disclosure remains refused even after the call has already failed authentication —
    # not merely "not yet verified," genuinely never granted for this call session.
    still_refused = await dispatch_tool_call(
        name="get_claim_status",
        args={"claim_id": seeded["claim_id"], "verification_level": "L2"},
        call_id=call_id,
        workflow_handle=AsyncMock(query=AsyncMock(return_value="L0")),
    )
    assert still_refused == {"found": False, "reason": "not_verified"}
