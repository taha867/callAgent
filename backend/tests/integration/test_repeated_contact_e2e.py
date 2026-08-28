"""REPEATED_CONTACT (.claude/plans/phase-3-backend-implementation-plan.md Batch 8 item 3,
spec §18/§31) — a deterministic prior-attempt-count check made once at call start, not an
LLM inference. Seeds 2 prior CallAttempt rows for the same (customer_id, claim_id); the 3rd
real workflow execution's own create_call_attempt makes it the 3rd within the window
(REPEATED_CONTACT_THRESHOLD=3), which must produce a call-start SentimentEvent row.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from src.calls.models import CallAttempt, SentimentEvent
from tests.integration.test_phase1_e2e import (
    _seed_customer_and_claim,
    _start,
    worker,  # noqa: F401 -- reused as a fixture via the `worker` parameter below
)

pytestmark = pytest.mark.integration


async def _seed_prior_attempt(db, *, seeded: dict, suffix: str, days_ago: int) -> None:
    db.add(
        CallAttempt(
            id=f"CALL-PRIOR-{suffix}",
            customer_id=seeded["customer_id"],
            claim_id=seeded["claim_id"],
            attempted_at=datetime.now() - timedelta(days=days_ago),
            disposition_code=None,
        )
    )
    await db.commit()


async def test_third_attempt_within_window_flags_repeated_contact(
    worker, temporal_env, db_session_committed
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="REPEAT")
    await _seed_prior_attempt(db_session_committed, seeded=seeded, suffix="1", days_ago=10)
    await _seed_prior_attempt(db_session_committed, seeded=seeded, suffix="2", days_ago=5)

    call_id = "CALL-E2E-REPEAT"
    handle = await _start(temporal_env, call_id, seeded, simulated_answer_result="NO_ANSWER")
    await handle.result()

    result = await db_session_committed.execute(
        select(SentimentEvent).where(
            SentimentEvent.call_attempt_id == call_id,
            SentimentEvent.signal == "REPEATED_CONTACT",
        )
    )
    assert result.scalar_one_or_none() is not None


async def test_first_attempt_does_not_flag_repeated_contact(
    worker, temporal_env, db_session_committed
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="FIRSTCALL")

    call_id = "CALL-E2E-FIRSTCALL"
    handle = await _start(temporal_env, call_id, seeded, simulated_answer_result="NO_ANSWER")
    await handle.result()

    result = await db_session_committed.execute(
        select(SentimentEvent).where(
            SentimentEvent.call_attempt_id == call_id,
            SentimentEvent.signal == "REPEATED_CONTACT",
        )
    )
    assert result.scalar_one_or_none() is None
