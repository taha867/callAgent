"""AdversarialScenarioId.TELEPHONY_FAILURE_MID_CALL. classify_answer (spec §5, task 4's
answer-detection stub) simply returns whatever simulated_answer_result the caller supplies
— a real telephony vendor adapter (Phase 2/6) replaces its body only, the workflow-side
contract stays a plain str. Passing "FAILED" is the existing, real mechanism for a telephony
failure before any conversation starts -> CallState.FAILED -> NETWORK_FAILURE.
"""

from src.calls.constants import DispositionCode
from tests.scripted_conversations.conftest import _seed_customer_and_claim, _start


async def test_telephony_failure_before_answer_resolves_to_network_failure(
    worker, temporal_env, db_session_committed
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="TELFAIL")
    call_id = "CALL-P4SC-TELFAIL"
    handle = await _start(temporal_env, call_id, seeded, simulated_answer_result="FAILED")

    result = await handle.result()
    assert result.disposition_code == DispositionCode.NETWORK_FAILURE.value
