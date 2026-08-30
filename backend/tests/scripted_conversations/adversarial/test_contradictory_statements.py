"""AdversarialScenarioId.CONTRADICTORY_STATEMENTS — "repeated questions / contradictory
customer statements." _run_right_party_check's own docstring states it loops rather than
acting on the first signal, deliberately ignoring a signal "not relevant to this stage yet"
(e.g. a stray ASK_QUESTION arriving before RIGHT_PARTY_CONFIRMED) rather than misreading it
as confirmation. This test proves that continue-and-keep-waiting behavior with a genuinely
irrelevant signal ahead of the real one.
"""

from src.calls.constants import DispositionCode
from src.calls.schemas import CustomerIntentSignal
from src.calls.workflows import CallSessionWorkflow
from tests.scripted_conversations.conftest import _seed_customer_and_claim, _start


async def test_an_irrelevant_signal_ahead_of_the_real_one_is_ignored_not_misread(
    worker, temporal_env, db_session_committed
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="CONTRADICT")
    call_id = "CALL-P4SC-CONTRADICT"
    handle = await _start(temporal_env, call_id, seeded)

    # ASK_QUESTION is not one of _run_right_party_check's recognized intents — the stage
    # must `continue` past it, not treat it as confirmation or an error.
    await handle.signal(
        CallSessionWorkflow.customer_utterance,
        CustomerIntentSignal(intent="ASK_QUESTION", topic="ETA"),
    )
    await handle.signal(
        CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="WRONG_PARTY")
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.WRONG_PARTY.value
