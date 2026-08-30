"""Shared fixtures for the Phase 4 scripted-conversation regression suite
(.claude/specs/phase-4-backend-spec.md §4.1). Reuses tests/conftest.py's
`db_session_committed` (real commits, so a Temporal activity running in its own session
sees them — required because these tests run real Temporal workflows, same reasoning as
tests/integration/test_phase2_pipeline_signal_bridge.py) and
tests/integration/conftest.py's `temporal_env`.

A `worker` fixture and `_seed_customer_and_claim` helper follow that same precedent test's
exact shape, extended with an optional `delay_flag` (Demo 6 needs a claim seeded with
delay_flag=True — spec §18's CLAIM_DELAY_ESCALATION gate).

`report_journey_run` is a best-effort fixture every journeys/*.py and adversarial/*.py test
can call to log its own outcome into qa_journey_run_result (spec §0.6) — a failure in this
reporting call must never fail the actual test, so it's wrapped in try/except.
"""

import logging

import pytest
import pytest_asyncio
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from src.calls.activities import ALL_CALLS_ACTIVITIES
from src.calls.workflows import CallSessionWorkflow
from src.complaints.activities import ALL_COMPLAINTS_ACTIVITIES
from src.complaints.workflows import ComplaintSlaMonitorWorkflow
from src.config import settings
from src.customers.service import hash_factor_value
from src.workflow_runner import SANDBOXED_WORKFLOW_RUNNER

pytestmark = pytest.mark.integration

_TASK_QUEUE = "phase4-scripted-conversations"

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def temporal_env():
    """Duplicated from tests/integration/conftest.py — conftest fixtures don't cross
    sibling directories, and tests/scripted_conversations/ is a sibling of tests/integration/,
    not a descendant of it, so this module needs its own copy rather than relying on pytest
    to find the other directory's conftest.py."""
    try:
        client = await Client.connect(
            settings.TEMPORAL_HOST,
            namespace=settings.TEMPORAL_NAMESPACE,
            data_converter=pydantic_data_converter,
        )
        env = WorkflowEnvironment.from_client(client)
    except RuntimeError:
        env = await WorkflowEnvironment.start_local(data_converter=pydantic_data_converter)

    yield env
    await env.shutdown()


async def _seed_customer_and_claim(
    db, *, suffix: str, factor_value: str = "1990", delay_flag: bool = False
) -> dict:
    from src.claims.constants import ClaimStage
    from src.claims.models import MotorClaim, MotorPolicy
    from src.customers.models import Customer, CustomerAuthFactor

    customer_id = f"CUST-P4SC-{suffix}"
    db.add(Customer(id=customer_id, full_name="Scripted Test", phone_e164=f"+9716{suffix}"))
    await db.flush()
    db.add(
        CustomerAuthFactor(
            id=f"FACTOR-P4SC-{suffix}",
            customer_id=customer_id,
            factor_type="BIRTH_MONTH_YEAR",
            factor_value_hash=hash_factor_value(factor_value),
        )
    )
    db.add(
        MotorPolicy(
            id=f"POL-P4SC-{suffix}",
            customer_id=customer_id,
            policy_number="P1",
            vehicle_plate="X",
            vehicle_make_model="Y",
        )
    )
    await db.flush()
    claim_id = f"CLM-P4SC-{suffix}"
    db.add(
        MotorClaim(
            id=claim_id,
            policy_id=f"POL-P4SC-{suffix}",
            customer_id=customer_id,
            claim_stage=ClaimStage.CLAIM_DELAYED if delay_flag else ClaimStage.REPAIR_AUTHORIZED,
            delay_flag=delay_flag,
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


async def _start(temporal_env, call_id: str, seeded: dict, **kwargs):
    from datetime import timedelta

    from src.calls.schemas import CallSessionInput

    return await temporal_env.client.start_workflow(
        CallSessionWorkflow.run,
        CallSessionInput(
            call_id=call_id, customer_id=seeded["customer_id"], claim_id=seeded["claim_id"], **kwargs
        ),
        id=f"call-session-{seeded['customer_id']}",
        task_queue=_TASK_QUEUE,
        execution_timeout=timedelta(seconds=60),
    )


async def _authenticate_to_follow_up(handle, *, factor_value: str = "1990"):
    """Drives the workflow to FOLLOW_UP — every journey past Demo 3/4 needs this."""
    from src.calls.schemas import CustomerIntentSignal

    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="RIGHT_PARTY_CONFIRMED"),
    )
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="AUTH_ANSWER", value=factor_value),
    )


@pytest.fixture
def report_journey_run(db_session_committed):
    """Best-effort — a failure here must never fail the actual scripted-conversation test
    (spec §0.6). Call as `await report_journey_run(demo_journey_id=..., passed=..., test_node_id=...)`."""

    async def _report(**kwargs) -> None:
        try:
            from src.qa import service as qa_service
            from src.qa.schemas import JourneyRunCreate

            await qa_service.record_journey_run(db_session_committed, JourneyRunCreate(**kwargs))
            await db_session_committed.commit()
        except Exception:
            logger.warning("report_journey_run failed (non-fatal)", exc_info=True)

    return _report
