"""The duration_seconds fix (.claude/plans/phase-3-backend-implementation-plan.md Batch 8
item 4 / spec §5.4): FinalizeOutcomeInput.duration_seconds already existed end-to-end since
Phase 1 — only calls/workflows.py::_finalize()'s call site never populated it. A full
scripted CallSessionWorkflow run must now leave CallAttempt.duration_seconds non-None.
"""

import pytest

from tests.integration.test_phase1_e2e import (
    _call_attempt,
    _seed_customer_and_claim,
    _start,
    worker,  # noqa: F401 -- reused as a fixture via the `worker` parameter below
)

pytestmark = pytest.mark.integration


async def test_duration_seconds_populated_after_finalize(
    worker, temporal_env, db_session_committed
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="DURATION")
    call_id = "CALL-E2E-DURATION"
    handle = await _start(temporal_env, call_id, seeded, simulated_answer_result="NO_ANSWER")

    await handle.result()

    attempt = await _call_attempt(db_session_committed, call_id)
    assert attempt.duration_seconds is not None
    assert attempt.duration_seconds >= 0
