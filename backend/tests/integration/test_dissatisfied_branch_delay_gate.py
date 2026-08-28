"""The DISSATISFIED-branch fix (.claude/plans/phase-3-backend-implementation-plan.md
Batch 8 item 1, spec §0.8/§18): calls/workflows.py's DISSATISFIED branch must gate
CLAIM_DELAY_ESCALATION on MotorClaim.delay_flag, falling back to CLAIMS_TEAM_QUERY when the
claim isn't actually delayed. The existing
tests/integration/test_phase1_e2e.py::test_dissatisfaction_creates_escalation_action only
asserts disposition_code == SUCCESS_ACTION_CREATED, which resolve_disposition produces
regardless of which action_code was chosen — it does NOT prove this fix. This file asserts
the actual ClaimAction.action_code for both delay_flag values.
"""

import pytest
from sqlalchemy import select

from src.actions.constants import ActionCode
from src.actions.models import ClaimAction
from src.calls.constants import DispositionCode
from src.calls.schemas import CustomerIntentSignal
from src.calls.workflows import CallSessionWorkflow
from src.claims.models import MotorClaim
from tests.integration.test_phase1_e2e import (
    _authenticate,
    _seed_customer_and_claim,
    _start,
    worker,  # noqa: F401 -- reused as a fixture via the `worker` parameter below
)

pytestmark = pytest.mark.integration


async def _set_delay_flag(db, claim_id: str, delay_flag: bool) -> None:
    claim = await db.get(MotorClaim, claim_id)
    claim.delay_flag = delay_flag
    await db.commit()


async def test_confirmed_delay_creates_claim_delay_escalation(
    worker, temporal_env, db_session_committed
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DELAY-TRUE")
    await _set_delay_flag(db_session_committed, seeded["claim_id"], delay_flag=True)

    call_id = "CALL-E2E-DELAY-TRUE"
    handle = await _start(temporal_env, call_id, seeded)
    await _authenticate(handle)
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="DISSATISFIED", summary="Waiting two weeks for approval"),
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.SUCCESS_ACTION_CREATED.value

    rows = (
        (
            await db_session_committed.execute(
                select(ClaimAction).where(ClaimAction.claim_id == seeded["claim_id"])
            )
        )
        .scalars()
        .all()
    )
    assert any(r.action_code == ActionCode.CLAIM_DELAY_ESCALATION for r in rows)
    assert not any(r.action_code == ActionCode.CLAIMS_TEAM_QUERY for r in rows)


async def test_unconfirmed_delay_creates_claims_team_query_not_escalation(
    worker, temporal_env, db_session_committed
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DELAY-FALSE")
    await _set_delay_flag(db_session_committed, seeded["claim_id"], delay_flag=False)

    call_id = "CALL-E2E-DELAY-FALSE"
    handle = await _start(temporal_env, call_id, seeded)
    await _authenticate(handle)
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="DISSATISFIED", summary="This is unacceptable"),
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.SUCCESS_ACTION_CREATED.value

    rows = (
        (
            await db_session_committed.execute(
                select(ClaimAction).where(ClaimAction.claim_id == seeded["claim_id"])
            )
        )
        .scalars()
        .all()
    )
    assert any(r.action_code == ActionCode.CLAIMS_TEAM_QUERY for r in rows)
    assert not any(r.action_code == ActionCode.CLAIM_DELAY_ESCALATION for r in rows)
