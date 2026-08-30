"""AdversarialScenarioId.BARGE_IN — "interruptions / barge-in mid-sentence." Pipecat's own
VAD/turn-taking machinery (SileroVADAnalyzer, LLMContextAggregatorPair) handles audio-level
interruption; the piece this codebase's own code controls and can be tested without real
audio is CallSessionWorkflow._wait_for_signal's own documented guarantee (workflows.py's
docstring): two signals arriving with no `await` in between (e.g. a customer starting a new
utterance before the first one's processing settled) must both be observable in order, never
silently overwritten.
"""

import asyncio

from sqlalchemy import select

from src.calls.constants import DispositionCode
from src.calls.models import CustomerIntent
from src.calls.schemas import CustomerIntentSignal
from src.calls.workflows import CallSessionWorkflow
from tests.scripted_conversations.conftest import _seed_customer_and_claim, _start


async def test_two_rapid_signals_with_no_await_in_between_are_both_observed_in_order(
    worker, temporal_env, db_session_committed
):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="BARGEIN")
    call_id = "CALL-P4SC-BARGEIN"
    handle = await _start(temporal_env, call_id, seeded)

    # Fired concurrently, matching the workflow docstring's own "no await in between" claim
    # — gather, not two sequential awaited calls.
    await asyncio.gather(
        handle.signal(
            CallSessionWorkflow.customer_utterance,
            CustomerIntentSignal(intent="RIGHT_PARTY_CONFIRMED"),
        ),
        handle.signal(
            CallSessionWorkflow.customer_utterance,
            CustomerIntentSignal(intent="AUTH_ANSWER", value="1990"),
        ),
    )
    await handle.signal(
        CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="NOTHING_ELSE")
    )

    result = await handle.result()
    assert result.disposition_code == DispositionCode.SUCCESS_STATUS_DELIVERED.value

    rows = (
        (
            await db_session_committed.execute(
                select(CustomerIntent)
                .where(CustomerIntent.call_attempt_id == call_id)
                .order_by(CustomerIntent.created_at)
            )
        )
        .scalars()
        .all()
    )
    intents = [r.intent for r in rows]
    assert "RIGHT_PARTY_CONFIRMED" in intents
    assert "AUTH_ANSWER" in intents
    # Neither signal was dropped nor silently overwritten by the other arriving concurrently.
    assert intents.index("RIGHT_PARTY_CONFIRMED") < intents.index("AUTH_ANSWER")
