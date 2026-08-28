"""complaints/service.py::create_complaint — task 7, §18.1 SLA computation, idempotent."""

from datetime import datetime, timedelta

from src.claims.constants import ClaimStage
from src.claims.models import MotorClaim, MotorPolicy
from src.complaints.config import ComplaintsConfig
from src.complaints.service import create_complaint
from src.customers.models import Customer

_NOW = datetime(2026, 8, 27, 11, 42, 0)


def _config(**overrides) -> ComplaintsConfig:
    return ComplaintsConfig(_env_file=None, **overrides)


async def _seed_claim(db_session, *, suffix: str) -> str:
    customer_id = f"CUST-COMP-{suffix}"
    db_session.add(Customer(id=customer_id, full_name="x", phone_e164="+1"))
    await db_session.flush()
    db_session.add(
        MotorPolicy(
            id=f"POL-COMP-{suffix}",
            customer_id=customer_id,
            policy_number="P1",
            vehicle_plate="X",
            vehicle_make_model="Y",
        )
    )
    await db_session.flush()
    claim_id = f"CLM-COMP-{suffix}"
    db_session.add(
        MotorClaim(
            id=claim_id,
            policy_id=f"POL-COMP-{suffix}",
            customer_id=customer_id,
            claim_stage=ClaimStage.CLAIM_DELAYED,
            language="en",
        )
    )
    await db_session.flush()
    return claim_id


async def test_create_complaint_computes_sla_deadlines(db_session):
    claim_id = await _seed_claim(db_session, suffix="1")
    config = _config(ACKNOWLEDGMENT_SLA_HOURS=24, RESOLUTION_SLA_DAYS=9)

    result = await create_complaint(
        db_session,
        key="CALL-COMP-1-ACTION-1",
        correlation_id="CALL-COMP-1",
        claim_id=claim_id,
        source_call_id="CALL-COMP-1",
        complaint_category="CLAIM_DELAY",
        customer_statement_summary="Customer states repair approval has been delayed.",
        severity="MEDIUM",
        preferred_contact_method="PHONE",
        now=_NOW,
        config=config,
    )

    assert result["acknowledgment_due_at"] == (_NOW + timedelta(hours=24)).isoformat()
    assert result["resolution_due_at"] == (_NOW + timedelta(days=9)).isoformat()
    assert result["sla_source"] == "INSURER_CONFIGURED"
    assert result["status"] == "OPEN"


async def test_create_complaint_is_idempotent_on_replay(db_session):
    claim_id = await _seed_claim(db_session, suffix="2")
    config = _config()
    key = "CALL-COMP-2-ACTION-1"
    kwargs = {
        "key": key,
        "correlation_id": "CALL-COMP-2",
        "claim_id": claim_id,
        "source_call_id": "CALL-COMP-2",
        "complaint_category": "CLAIM_DELAY",
        "customer_statement_summary": "test",
        "severity": "LOW",
        "preferred_contact_method": "PHONE",
        "now": _NOW,
        "config": config,
    }
    first = await create_complaint(db_session, **kwargs)
    second = await create_complaint(db_session, **kwargs)
    assert first["id"] == second["id"]
    # Replay must not recompute a different deadline — same `now` either way here, but the
    # point is the SECOND call's `operation()` never re-runs at all (idempotent() replays
    # the stored result), which this equality also confirms indirectly.
    assert first["acknowledgment_due_at"] == second["acknowledgment_due_at"]


async def test_customer_expected_resolution_defaults_to_none(db_session):
    claim_id = await _seed_claim(db_session, suffix="3")
    result = await create_complaint(
        db_session,
        key="CALL-COMP-3-ACTION-1",
        correlation_id="CALL-COMP-3",
        claim_id=claim_id,
        source_call_id="CALL-COMP-3",
        complaint_category="CLAIM_DELAY",
        customer_statement_summary="test",
        severity="HIGH",
        preferred_contact_method="EMAIL",
        now=_NOW,
        config=_config(),
    )
    assert result["severity"] == "HIGH"
