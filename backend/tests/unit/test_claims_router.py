"""claims/router.py — task 3's mock claims API. Exercises the real registered app
(src.main.app), overriding get_db with the test's rollback-isolated session — proves the
router, dependency, and service are wired together correctly, not just the service alone.
"""

import httpx
import pytest

from src.claims.constants import ClaimStage
from src.claims.models import ClaimDocument, MotorClaim, MotorPolicy, RepairGarage
from src.customers.models import Customer
from src.database import get_db
from src.main import app


@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


async def _seed_claim(db_session, *, suffix: str, **claim_overrides) -> str:
    customer_id = f"CUST-ROUTER-{suffix}"
    db_session.add(Customer(id=customer_id, full_name="x", phone_e164="+1"))
    await db_session.flush()
    db_session.add(
        MotorPolicy(
            id=f"POL-ROUTER-{suffix}",
            customer_id=customer_id,
            policy_number="P1",
            vehicle_plate="X",
            vehicle_make_model="Y",
        )
    )
    await db_session.flush()
    claim_id = f"CLM-ROUTER-{suffix}"
    defaults = {
        "id": claim_id,
        "policy_id": f"POL-ROUTER-{suffix}",
        "customer_id": customer_id,
        "claim_stage": ClaimStage.REPAIR_AUTHORIZED,
        "language": "en",
    }
    defaults.update(claim_overrides)
    db_session.add(MotorClaim(**defaults))
    await db_session.flush()
    return claim_id


async def test_get_claim_returns_full_claim(client, db_session):
    claim_id = await _seed_claim(db_session, suffix="1")
    response = await client.get(f"/claims/{claim_id}")
    assert response.status_code == 200
    assert response.json()["id"] == claim_id


async def test_get_claim_404_for_missing_claim(client):
    response = await client.get("/claims/CLM-DOES-NOT-EXIST")
    assert response.status_code == 404


async def test_get_claim_status_redacts_settlement_below_l2(client, db_session):
    claim_id = await _seed_claim(
        db_session,
        suffix="2",
        claim_stage=ClaimStage.SETTLEMENT_APPROVED,
        settlement_amount="5000.00",
    )
    response = await client.get(f"/claims/{claim_id}/status", params={"verification_level": "L0"})
    assert response.status_code == 200
    assert response.json()["settlement_amount"] is None


async def test_get_claim_status_discloses_settlement_at_l2(client, db_session):
    claim_id = await _seed_claim(
        db_session,
        suffix="3",
        claim_stage=ClaimStage.SETTLEMENT_APPROVED,
        settlement_amount="5000.00",
    )
    response = await client.get(f"/claims/{claim_id}/status", params={"verification_level": "L2"})
    assert response.status_code == 200
    assert response.json()["settlement_amount"] == "5000.00"


async def test_get_claim_status_defaults_to_l0(client, db_session):
    claim_id = await _seed_claim(
        db_session, suffix="4", claim_stage=ClaimStage.SETTLEMENT_APPROVED, settlement_amount="1.00"
    )
    response = await client.get(f"/claims/{claim_id}/status")
    assert response.status_code == 200
    assert response.json()["settlement_amount"] is None


async def test_get_claim_timeline(client, db_session):
    from src.claims.models import ClaimStatusEvent

    claim_id = await _seed_claim(db_session, suffix="5")
    db_session.add(
        ClaimStatusEvent(
            id="EVT-ROUTER-1", claim_id=claim_id, to_stage=ClaimStage.REPAIR_AUTHORIZED
        )
    )
    await db_session.flush()

    response = await client.get(f"/claims/{claim_id}/timeline")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["to_stage"] == "REPAIR_AUTHORIZED"


async def test_get_claim_documents(client, db_session):
    claim_id = await _seed_claim(db_session, suffix="6")
    db_session.add(
        ClaimDocument(id="DOC-ROUTER-1", claim_id=claim_id, document_type="POLICE_REPORT")
    )
    await db_session.flush()

    response = await client.get(f"/claims/{claim_id}/documents")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["document_type"] == "POLICE_REPORT"


async def test_get_claim_garage_present(client, db_session):
    db_session.add(RepairGarage(id="GAR-ROUTER-1", name="Al Futtaim Auto Care"))
    await db_session.flush()
    claim_id = await _seed_claim(db_session, suffix="7", garage_id="GAR-ROUTER-1")

    response = await client.get(f"/claims/{claim_id}/garage")
    assert response.status_code == 200
    assert response.json()["name"] == "Al Futtaim Auto Care"


async def test_get_claim_garage_absent(client, db_session):
    claim_id = await _seed_claim(db_session, suffix="8")
    response = await client.get(f"/claims/{claim_id}/garage")
    assert response.status_code == 200
    assert response.json() is None
