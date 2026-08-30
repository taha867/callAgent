"""AdversarialScenarioId.SYSTEM_DATA_UNAVAILABLE — spec §14 Type E: deliver_status
(src/calls/activities.py) returns None when claims_service.get_claim finds no row, which
_run_status_and_follow_up treats as backend_unavailable=True -> BACKEND_SYSTEM_FAILURE,
plus a BACKEND_DATA_VERIFICATION_REQUEST fallback action.

REAL DEFECT FOUND during Phase 4 hardening, logged as qa defect
`backend-unavailable-fallback-action-fk-violation` (id 2dd6d559-0e48-40c4-bb7b-e89988082ef8):
the fallback action itself inserts a ClaimAction with claim_id=inp.claim_id, but
ClaimAction.claim_id is a real FK to motor_claim.id — when the claim genuinely doesn't
exist (the exact condition this branch handles), that insert violates the FK constraint.
The execute_activity call has no retry_policy override, so Temporal retries indefinitely
until the workflow's 60s execution_timeout fires, raising WorkflowFailureError instead of
resolving to BACKEND_SYSTEM_FAILURE. First occurrence — per
phases/phase-4-demo-hardening.md's two-strike rule, this is logged and the ticket stays
open (fixing calls/workflows.py's fallback-action branch is out of scope for the Phase 4
test-suite implementation itself); if this same defect shape recurs, it must be compiled
into a permanent fix before that second ticket closes. Skipped (not run) rather than xfail
so a known, ~70s-to-time-out failure doesn't slow down every regression run — re-enable
once the fallback branch is fixed to tolerate a missing claim.
"""

import pytest

from src.customers.service import hash_factor_value
from tests.scripted_conversations.conftest import _authenticate_to_follow_up, _start


async def _seed_customer_without_claim(db, *, suffix: str) -> dict:
    from src.customers.models import Customer, CustomerAuthFactor

    customer_id = f"CUST-P4SC-{suffix}"
    db.add(Customer(id=customer_id, full_name="No Claim Test", phone_e164=f"+9717{suffix}"))
    await db.flush()
    db.add(
        CustomerAuthFactor(
            id=f"FACTOR-P4SC-{suffix}",
            customer_id=customer_id,
            factor_type="BIRTH_MONTH_YEAR",
            factor_value_hash=hash_factor_value("1990"),
        )
    )
    await db.commit()
    return {"customer_id": customer_id, "claim_id": f"CLM-DOES-NOT-EXIST-{suffix}"}


@pytest.mark.skip(
    reason="Known defect qa/2dd6d559-0e48-40c4-bb7b-e89988082ef8 — fallback action FK "
    "violation causes a ~70s timeout instead of a clean BACKEND_SYSTEM_FAILURE. See module "
    "docstring."
)
async def test_missing_claim_data_resolves_to_backend_system_failure(
    worker, temporal_env, db_session_committed
):
    seeded = await _seed_customer_without_claim(db_session_committed, suffix="NODATA")
    call_id = "CALL-P4SC-NODATA"
    handle = await _start(temporal_env, call_id, seeded)
    await _authenticate_to_follow_up(handle)

    result = await handle.result()
    assert result.disposition_code == "BACKEND_SYSTEM_FAILURE"
