"""AdversarialScenarioId.INVALID_UNAUTHORIZED_CLI — spec §4.1. campaigns/service.py::
check_call_eligibility rejects a call attempt when no active, trunk-authorized CLI is
configured, reporting ineligible_reason="INVALID_OR_UNAUTHORIZED_CLI" — before any dial.
Uses db_session (rollback-isolated), not seeded_db, specifically so no
TelephonyCliConfiguration row exists yet.
"""

from datetime import datetime

from src.calls.constants import DispositionCode
from src.campaigns import service as campaigns_service
from tests.scripted_conversations.conftest import _seed_customer_and_claim


async def test_no_configured_cli_is_ineligible(db_session):
    seeded = await _seed_customer_and_claim(db_session, suffix="NOCLI")
    eligibility = await campaigns_service.check_call_eligibility(
        db_session,
        customer_id=seeded["customer_id"],
        claim_id=seeded["claim_id"],
        at=datetime(2026, 9, 1, 10, 0, 0),
    )
    assert eligibility.call_eligible is False
    assert eligibility.ineligible_reason == DispositionCode.INVALID_OR_UNAUTHORIZED_CLI.value
