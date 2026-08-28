"""actions/router.py + complaints/router.py — Batch 15's remaining API surface. Same
dependency-override pattern as test_claims_router.py: exercises the real registered app
(src.main.app), overriding get_db with the test's rollback-isolated session.

complaints/router.py's POST /complaints also starts ComplaintSlaMonitorWorkflow via a real
Temporal client — these tests are marked integration and need Temporal reachable.
"""

import httpx
import pytest

from src.claims.constants import ClaimStage
from src.claims.models import MotorClaim, MotorPolicy
from src.customers.models import Customer
from src.database import get_db
from src.main import app

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


async def _seed_claim(db_session, *, suffix: str) -> str:
    customer_id = f"CUST-ARTR-{suffix}"
    db_session.add(Customer(id=customer_id, full_name="x", phone_e164="+1"))
    await db_session.flush()
    db_session.add(
        MotorPolicy(
            id=f"POL-ARTR-{suffix}",
            customer_id=customer_id,
            policy_number="P1",
            vehicle_plate="X",
            vehicle_make_model="Y",
        )
    )
    await db_session.flush()
    claim_id = f"CLM-ARTR-{suffix}"
    db_session.add(
        MotorClaim(
            id=claim_id,
            policy_id=f"POL-ARTR-{suffix}",
            customer_id=customer_id,
            claim_stage=ClaimStage.DOCUMENTS_PENDING,
            language="en",
        )
    )
    await db_session.flush()
    return claim_id


async def test_create_action_via_router(client, db_session):
    claim_id = await _seed_claim(db_session, suffix="1")
    response = await client.post(
        f"/claims/{claim_id}/actions",
        json={
            "claim_id": claim_id,
            "action_code": "DOCUMENT_STATUS_DISPUTE",
            "summary": "dispute",
        },
        headers={"Idempotency-Key": f"{claim_id}-ACTION-1"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["claim_id"] == claim_id
    assert body["action_code"] == "DOCUMENT_STATUS_DISPUTE"


async def test_create_action_missing_idempotency_key_is_rejected(client, db_session):
    claim_id = await _seed_claim(db_session, suffix="2")
    response = await client.post(
        f"/claims/{claim_id}/actions",
        json={"claim_id": claim_id, "action_code": "DOCUMENT_STATUS_DISPUTE", "summary": "x"},
    )
    assert response.status_code == 422  # missing required header


async def test_create_action_404_for_missing_claim(client):
    response = await client.post(
        "/claims/CLM-DOES-NOT-EXIST/actions",
        json={
            "claim_id": "CLM-DOES-NOT-EXIST",
            "action_code": "DOCUMENT_STATUS_DISPUTE",
            "summary": "x",
        },
        headers={"Idempotency-Key": "X-ACTION-1"},
    )
    assert response.status_code == 404


async def test_create_escalation_via_router(client, db_session):
    claim_id = await _seed_claim(db_session, suffix="3")
    response = await client.post(
        f"/claims/{claim_id}/escalations",
        json={"call_id": "CALL-ARTR-3", "reason": "CUSTOMER_REQUESTED_HUMAN"},
        headers={"Idempotency-Key": "CALL-ARTR-3-ACTION-1"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["reason"] == "CUSTOMER_REQUESTED_HUMAN"


async def test_create_complaint_via_router_and_starts_sla_monitor(client, db_session):
    claim_id = await _seed_claim(db_session, suffix="4")
    response = await client.post(
        "/complaints",
        json={
            "claim_id": claim_id,
            "source_call_id": "CALL-ARTR-4",
            "complaint_category": "CLAIM_DELAY",
            "customer_statement_summary": "test",
            "severity": "MEDIUM",
            "preferred_contact_method": "PHONE",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["claim_id"] == claim_id
    assert body["acknowledgment_due_at"] is not None
    assert body["resolution_due_at"] is not None

    get_response = await client.get(f"/complaints/{body['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == body["id"]


async def test_get_complaint_404_for_missing(client):
    response = await client.get("/complaints/COMP-DOES-NOT-EXIST")
    assert response.status_code == 404
