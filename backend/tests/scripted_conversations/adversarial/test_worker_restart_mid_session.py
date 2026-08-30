"""AdversarialScenarioId.WORKER_RESTART_MID_SESSION — "orchestrator/worker restart during
an active live session." The actual mechanism here is Temporal's own durability guarantee
(workflow state is persisted server-side, independent of any one worker process) — spec
§10.6.2 relies on that guarantee directly rather than any custom checkpointing code in this
repo (CLAUDE.md §2.6).

This test does NOT use the shared `worker` fixture (a second Worker registered on the same
task queue while the first is still running is itself rejected by the Temporal SDK — "worker
task types... not allowed" — confirmed by trying it: a real restart requires the first
worker to actually stop before a second starts, which is exactly what this test does). It
starts a call under a first, short-lived Worker, stops that worker (simulating a
crash/restart), then starts a second, independent Worker on the same task queue and confirms
the workflow resumes and completes correctly — proving this repo's own workflow/activity
registration doesn't depend on any one worker process's in-memory state.
"""

from temporalio.worker import Worker

from src.calls.activities import ALL_CALLS_ACTIVITIES
from src.calls.constants import DispositionCode
from src.calls.schemas import CallSessionInput, CustomerIntentSignal
from src.calls.workflows import CallSessionWorkflow
from src.complaints.activities import ALL_COMPLAINTS_ACTIVITIES
from src.complaints.workflows import ComplaintSlaMonitorWorkflow
from src.workflow_runner import SANDBOXED_WORKFLOW_RUNNER
from tests.scripted_conversations.conftest import _seed_customer_and_claim

_TASK_QUEUE = "phase4-worker-restart"


def _build_worker(client):
    return Worker(
        client,
        task_queue=_TASK_QUEUE,
        workflows=[CallSessionWorkflow, ComplaintSlaMonitorWorkflow],
        activities=[*ALL_CALLS_ACTIVITIES, *ALL_COMPLAINTS_ACTIVITIES],
        workflow_runner=SANDBOXED_WORKFLOW_RUNNER,
    )


async def test_a_second_worker_can_resume_after_the_first_stops(temporal_env, db_session_committed):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="RESTARTV2")
    call_id = "CALL-P4SC-RESTARTV2"

    async with _build_worker(temporal_env.client):
        handle = await temporal_env.client.start_workflow(
            CallSessionWorkflow.run,
            CallSessionInput(
                call_id=call_id, customer_id=seeded["customer_id"], claim_id=seeded["claim_id"]
            ),
            id=f"call-session-{seeded['customer_id']}",
            task_queue=_TASK_QUEUE,
        )
        await handle.signal(
            CallSessionWorkflow.customer_utterance,
            CustomerIntentSignal(intent="RIGHT_PARTY_CONFIRMED"),
        )
        # give the first worker a moment to actually process the signal before it stops
        import asyncio

        for _ in range(50):
            if await handle.query(CallSessionWorkflow.current_state) == "AUTHENTICATION":
                break
            await asyncio.sleep(0.1)
    # first worker's `async with` block has exited here — it has fully stopped polling.

    async with _build_worker(temporal_env.client):
        await handle.signal(
            CallSessionWorkflow.customer_utterance,
            CustomerIntentSignal(intent="AUTH_ANSWER", value="1990"),
        )
        await handle.signal(
            CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="NOTHING_ELSE")
        )
        result = await handle.result()

    assert result.disposition_code == DispositionCode.SUCCESS_STATUS_DELIVERED.value
