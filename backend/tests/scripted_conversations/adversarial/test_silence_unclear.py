"""AdversarialScenarioId.SILENCE_UNCLEAR — "silence / unclear answers." True silence is
already the DTMF_FALLBACK_TRIGGERED mechanism (a run of empty transcriptions). An unclear
*spoken* answer during authentication is the other real path: verify_level1 returns NO_MATCH
when the supplied value doesn't hash-match, and — as long as attempts_so_far is still below
MAX_AUTH_ATTEMPTS — the workflow loops and asks again rather than failing outright (spec
§10.4's "let's try one other verification method"). This test proves that recovery: an
unclear/wrong first answer, then a correct second one, reaches AUTHENTICATED normally.
"""

from src.calls.constants import DispositionCode
from src.calls.schemas import CustomerIntentSignal
from src.calls.workflows import CallSessionWorkflow
from src.verification.constants import MAX_AUTH_ATTEMPTS
from tests.scripted_conversations.conftest import _seed_customer_and_claim, _start


async def test_one_unclear_wrong_answer_then_a_correct_one_still_authenticates(
    worker, temporal_env, db_session_committed
):
    assert MAX_AUTH_ATTEMPTS > 1  # otherwise this recovery path can't exist
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="UNCLEAR", factor_value="1990")
    call_id = "CALL-P4SC-UNCLEAR"
    handle = await _start(temporal_env, call_id, seeded)
    await handle.signal(
        CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="RIGHT_PARTY_CONFIRMED")
    )
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="AUTH_ANSWER", value="mumbled, unclear"),
    )
    await handle.signal(
        CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="AUTH_ANSWER", value="1990")
    )
    await handle.signal(
        CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="NOTHING_ELSE")
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.SUCCESS_STATUS_DELIVERED.value
