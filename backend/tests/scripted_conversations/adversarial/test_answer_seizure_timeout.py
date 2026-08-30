"""AdversarialScenarioId.ANSWER_SEIZURE_TIMEOUT — "silent-call failure." An answer result
telephony can't classify (no real seizure-timeout simulation exists in this Phase 1 stub —
classify_answer just forwards whatever simulated_answer_result it's given) falls through
CallSessionWorkflow.run()'s `CallState(answer_result) if answer_result in CallState else
CallState.FAILED` guard -> NETWORK_FAILURE, the same safe-fallback path
test_telephony_failure_mid_call.py exercises via the literal "FAILED" value. This test uses
a deliberately unrecognized value to prove the *fallback* itself, not just the FAILED enum
member.
"""

from src.calls.constants import DispositionCode
from tests.scripted_conversations.conftest import _seed_customer_and_claim, _start


async def test_unrecognized_answer_result_falls_back_to_network_failure(
    worker, temporal_env, db_session_committed
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="SEIZURE")
    call_id = "CALL-P4SC-SEIZURE"
    handle = await _start(
        temporal_env, call_id, seeded, simulated_answer_result="ANSWER_SEIZURE_TIMEOUT"
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.NETWORK_FAILURE.value
