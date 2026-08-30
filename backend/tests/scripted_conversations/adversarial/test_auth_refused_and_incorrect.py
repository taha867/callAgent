"""AdversarialScenarioId.AUTH_REFUSED / AUTH_INCORRECT_BOTH_ATTEMPTS.

"Customer refuses authentication" -> the workflow has no dedicated AUTH_REFUSED branch
(DispositionCode.AUTH_REFUSED exists as an enum member but is never produced by
resolve_disposition — confirmed via calls/disposition.py) — the real, existing mechanism a
refusal takes is REQUEST_HUMAN during the AUTHENTICATION stage -> SUCCESS_HUMAN_TRANSFER.
This test exercises that actual behavior rather than asserting a disposition code nothing
in the codebase produces yet.

"Incorrect authentication (both attempts)" is exactly test_demo_4_authentication_failure.py
— not duplicated here.
"""

from src.calls.constants import DispositionCode
from src.calls.schemas import CustomerIntentSignal
from src.calls.workflows import CallSessionWorkflow
from tests.scripted_conversations.conftest import _seed_customer_and_claim, _start


async def test_customer_requests_human_during_authentication_instead_of_answering(
    worker, temporal_env, db_session_committed
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="AUTHREFUSE")
    call_id = "CALL-P4SC-AUTHREFUSE"
    handle = await _start(temporal_env, call_id, seeded)
    await handle.signal(
        CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="RIGHT_PARTY_CONFIRMED")
    )
    await handle.signal(
        CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="REQUEST_HUMAN")
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.SUCCESS_HUMAN_TRANSFER.value
