"""calls/router.py — GET /calls/{call_id}, GET /calls/{call_id}/outcome, POST /calls.
POST /calls starts a real CallSessionWorkflow via a Temporal client — needs Temporal
reachable, same as test_actions_and_complaints_router.py.
"""

import asyncio

import httpx
import pytest
from temporalio.worker import Worker

from src.calls.activities import ALL_CALLS_ACTIVITIES
from src.calls.workflows import CallSessionWorkflow
from src.campaigns.activities import ALL_CAMPAIGNS_ACTIVITIES
from src.campaigns.workflows import RetrySchedulerWorkflow
from src.claims.constants import ClaimStage
from src.claims.models import MotorClaim, MotorPolicy
from src.complaints.activities import ALL_COMPLAINTS_ACTIVITIES
from src.complaints.workflows import ComplaintSlaMonitorWorkflow
from src.config import settings
from src.customers.models import Customer
from src.database import get_db
from src.main import app
from src.workflow_runner import SANDBOXED_WORKFLOW_RUNNER

pytestmark = pytest.mark.integration


@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


async def _seed_claim(db_session, *, suffix: str) -> dict:
    customer_id = f"CUST-CROUTER-{suffix}"
    db_session.add(Customer(id=customer_id, full_name="x", phone_e164="+1"))
    await db_session.flush()
    db_session.add(
        MotorPolicy(
            id=f"POL-CROUTER-{suffix}",
            customer_id=customer_id,
            policy_number="P1",
            vehicle_plate="X",
            vehicle_make_model="Y",
        )
    )
    await db_session.flush()
    claim_id = f"CLM-CROUTER-{suffix}"
    db_session.add(
        MotorClaim(
            id=claim_id,
            policy_id=f"POL-CROUTER-{suffix}",
            customer_id=customer_id,
            claim_stage=ClaimStage.REPAIR_AUTHORIZED,
            language="en",
        )
    )
    await db_session.commit()
    return {"customer_id": customer_id, "claim_id": claim_id}


async def test_get_call_attempt_404_for_missing(client):
    response = await client.get("/calls/CALL-DOES-NOT-EXIST")
    assert response.status_code == 404


async def test_start_call_rejected_when_kill_switch_off(client, db_session, set_flags):
    set_flags(GLOBAL_OUTBOUND_ENABLED=False)
    seeded = await _seed_claim(db_session, suffix="KILL")
    response = await client.post(
        "/calls", json={"customer_id": seeded["customer_id"], "claim_id": seeded["claim_id"]}
    )
    assert response.status_code == 503


async def test_start_call_and_read_it_back(db_session_committed, temporal_env):
    """POST /calls starts a real CallSessionWorkflow whose activities write through their
    OWN independent session (get_session_factory(), not the FastAPI-injected one) — needs
    db_session_committed, not the plain client fixture's rollback-isolated db_session,
    for the same reason tests/integration/test_phase0_e2e.py does (see its own comments):
    a rollback-isolated session's writes are invisible to that independent session, and
    db_session_committed also monkeypatches src.database.SessionLocal to the test engine.

    Uses a UUID suffix, not a fixed one: this workflow runs against the real, persistent
    Temporal server (temporal_env tries settings.TEMPORAL_HOST first), so a fixed
    customer_id would collide with the still-running `call-session-{customer_id}` workflow
    execution left behind by a previous run of this same test.
    """
    import uuid

    async def override_get_db():
        yield db_session_committed

    app.dependency_overrides[get_db] = override_get_db
    try:
        seeded = await _seed_claim(db_session_committed, suffix=f"START-{uuid.uuid4().hex[:8]}")

        # Registers everything worker.py registers in production, not just
        # CallSessionWorkflow — POST /calls starts its workflow on the shared production
        # task queue (settings.TEMPORAL_TASK_QUEUE), which other tests' still-running
        # ComplaintSlaMonitorWorkflow/RetrySchedulerWorkflow executions may also be
        # polling; a worker registering only a subset chokes the moment the server hands
        # it a task for a type it doesn't recognize.
        async with Worker(
            temporal_env.client,
            task_queue=settings.TEMPORAL_TASK_QUEUE,
            workflows=[CallSessionWorkflow, RetrySchedulerWorkflow, ComplaintSlaMonitorWorkflow],
            activities=[
                *ALL_CALLS_ACTIVITIES,
                *ALL_CAMPAIGNS_ACTIVITIES,
                *ALL_COMPLAINTS_ACTIVITIES,
            ],
            workflow_runner=SANDBOXED_WORKFLOW_RUNNER,
        ):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/calls",
                    json={
                        "customer_id": seeded["customer_id"],
                        "claim_id": seeded["claim_id"],
                        "simulated_answer_result": "NO_ANSWER",
                    },
                )
                assert response.status_code == 200, response.text
                call_id = response.json()["call_id"]

                # Give the workflow a moment to run its first activity
                # (create_call_attempt) and reach a terminal state (NO_ANSWER finalizes
                # immediately, no signal needed).
                handle = temporal_env.client.get_workflow_handle(response.json()["workflow_id"])
                await asyncio.wait_for(handle.result(), timeout=10)

                get_response = await client.get(f"/calls/{call_id}")
                assert get_response.status_code == 200
                assert get_response.json()["id"] == call_id
                assert get_response.json()["disposition_code"] == "NO_ANSWER"

                outcome_response = await client.get(f"/calls/{call_id}/outcome")
                assert outcome_response.status_code == 200
                assert outcome_response.json()["disposition_code"] == "NO_ANSWER"
    finally:
        app.dependency_overrides.pop(get_db, None)
