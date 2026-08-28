"""campaigns/service.py::check_call_eligibility — spec §4, composing claims/telephony
reads. Plain db_session fixture, no Temporal involved.
"""

from datetime import date, datetime

from src.campaigns.service import check_call_eligibility
from src.claims.constants import ClaimStage
from src.claims.models import MotorClaim, MotorPolicy
from src.customers.models import Customer
from src.telephony.models import BusinessContactCalendar, TelephonyCliConfiguration

_NOW = datetime(2026, 8, 27, 10, 0, 0)


async def _seed_customer_and_claim(db_session, *, suffix: str) -> tuple[str, str]:
    customer_id = f"CUST-ELIG-{suffix}"
    db_session.add(Customer(id=customer_id, full_name="x", phone_e164="+1"))
    await db_session.flush()
    db_session.add(
        MotorPolicy(
            id=f"POL-ELIG-{suffix}",
            customer_id=customer_id,
            policy_number="P1",
            vehicle_plate="X",
            vehicle_make_model="Y",
        )
    )
    await db_session.flush()
    claim_id = f"CLM-ELIG-{suffix}"
    db_session.add(
        MotorClaim(
            id=claim_id,
            policy_id=f"POL-ELIG-{suffix}",
            customer_id=customer_id,
            claim_stage=ClaimStage.REPAIR_AUTHORIZED,
            language="en",
        )
    )
    await db_session.flush()
    return customer_id, claim_id


async def test_ineligible_when_claim_not_found(db_session):
    result = await check_call_eligibility(
        db_session, customer_id="CUST-X", claim_id="CLM-MISSING", at=_NOW
    )
    assert not result.call_eligible
    assert result.ineligible_reason == "CLAIM_NOT_FOUND"


async def test_ineligible_when_no_active_cli(db_session):
    customer_id, claim_id = await _seed_customer_and_claim(db_session, suffix="NOCLI")
    result = await check_call_eligibility(
        db_session, customer_id=customer_id, claim_id=claim_id, at=_NOW
    )
    assert not result.call_eligible
    assert result.ineligible_reason == "INVALID_OR_UNAUTHORIZED_CLI"


async def test_eligible_with_active_cli_and_open_calendar(db_session):
    customer_id, claim_id = await _seed_customer_and_claim(db_session, suffix="OK")
    db_session.add(
        TelephonyCliConfiguration(
            cli="+971500000000", owner="ABC_INSURANCE", trunk_authorized=True, is_active=True
        )
    )
    await db_session.flush()

    result = await check_call_eligibility(
        db_session, customer_id=customer_id, claim_id=claim_id, at=_NOW
    )
    assert result.call_eligible
    assert result.cli == "+971500000000"
    assert result.ineligible_reason is None


async def test_ineligible_cli_not_trunk_authorized(db_session):
    customer_id, claim_id = await _seed_customer_and_claim(db_session, suffix="UNAUTH")
    db_session.add(
        TelephonyCliConfiguration(
            cli="+971500000001", owner="ABC_INSURANCE", trunk_authorized=False, is_active=True
        )
    )
    await db_session.flush()

    result = await check_call_eligibility(
        db_session, customer_id=customer_id, claim_id=claim_id, at=_NOW
    )
    assert not result.call_eligible
    assert result.ineligible_reason == "INVALID_OR_UNAUTHORIZED_CLI"


async def test_ineligible_when_blackout_calendar_row_blocks_contact(db_session):
    customer_id, claim_id = await _seed_customer_and_claim(db_session, suffix="BLACKOUT")
    db_session.add(
        TelephonyCliConfiguration(
            cli="+971500000002", owner="ABC_INSURANCE", trunk_authorized=True, is_active=True
        )
    )
    db_session.add(
        BusinessContactCalendar(
            id="CAL-BLACKOUT-1",
            calendar_date=date(2026, 8, 27),
            calendar_type="BLACKOUT",
            contact_allowed=False,
        )
    )
    await db_session.flush()

    result = await check_call_eligibility(
        db_session, customer_id=customer_id, claim_id=claim_id, at=_NOW
    )
    assert not result.call_eligible
    assert result.ineligible_reason == "OUTSIDE_PERMITTED_CONTACT_WINDOW"


async def test_eligible_on_a_date_with_no_calendar_row_at_all(db_session):
    """Stub behavior per task 4: absence of a row means the normal contact window applies."""
    customer_id, claim_id = await _seed_customer_and_claim(db_session, suffix="NOROW")
    db_session.add(
        TelephonyCliConfiguration(
            cli="+971500000003", owner="ABC_INSURANCE", trunk_authorized=True, is_active=True
        )
    )
    await db_session.flush()

    result = await check_call_eligibility(
        db_session, customer_id=customer_id, claim_id=claim_id, at=_NOW
    )
    assert result.call_eligible
