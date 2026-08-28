"""RetrySchedulerWorkflow — the remaining 2 of 15 exit-criteria branches
(NO_ANSWER -> retry, CONCURRENT_CALL -> AI attempt aborted) that need the retry scheduler
rather than CallSessionWorkflow alone. See
.claude/specs/phase-1-backend-implementation-plan.md Batch 13/14.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select
from temporalio.worker import Worker

from src.calls.activities import ALL_CALLS_ACTIVITIES
from src.calls.constants import DispositionCode
from src.calls.schemas import CallSessionInput
from src.calls.workflows import CallSessionWorkflow
from src.campaigns.activities import ALL_CAMPAIGNS_ACTIVITIES
from src.campaigns.schemas import RetrySchedulerInput
from src.campaigns.workflows import RetrySchedulerWorkflow
from src.customers.service import hash_factor_value
from src.workflow_runner import SANDBOXED_WORKFLOW_RUNNER

pytestmark = pytest.mark.integration

_TASK_QUEUE = "phase1-retry-e2e"
_WORKFLOWS = [CallSessionWorkflow, RetrySchedulerWorkflow]
_ACTIVITIES = [*ALL_CALLS_ACTIVITIES, *ALL_CAMPAIGNS_ACTIVITIES]


async def _seed_customer_claim_and_cli(db, *, suffix: str, call_job_id: str) -> dict:
    from src.campaigns.models import CallJob, OutboundCampaign
    from src.claims.constants import ClaimStage
    from src.claims.models import MotorClaim, MotorPolicy
    from src.customers.models import Customer, CustomerAuthFactor
    from src.telephony.models import TelephonyCliConfiguration

    customer_id = f"CUST-RETRY-{suffix}"
    db.add(Customer(id=customer_id, full_name="x", phone_e164=f"+9715{suffix}"))
    await db.flush()
    db.add(
        CustomerAuthFactor(
            id=f"FACTOR-RETRY-{suffix}",
            customer_id=customer_id,
            factor_type="BIRTH_MONTH_YEAR",
            factor_value_hash=hash_factor_value("1990"),
        )
    )
    db.add(
        MotorPolicy(
            id=f"POL-RETRY-{suffix}",
            customer_id=customer_id,
            policy_number="P1",
            vehicle_plate="X",
            vehicle_make_model="Y",
        )
    )
    await db.flush()
    claim_id = f"CLM-RETRY-{suffix}"
    db.add(
        MotorClaim(
            id=claim_id,
            policy_id=f"POL-RETRY-{suffix}",
            customer_id=customer_id,
            claim_stage=ClaimStage.REPAIR_AUTHORIZED,
            language="en",
        )
    )
    db.add(
        TelephonyCliConfiguration(
            cli=f"+97150000{suffix}"[:16],
            owner="ABC_INSURANCE",
            trunk_authorized=True,
            is_active=True,
        )
    )
    # CallAttempt.call_job_id is a real FK to call_job.id — RetrySchedulerWorkflow always
    # passes inp.call_job_id through to every CallSessionInput it starts, so a real
    # OutboundCampaign + CallJob must exist for it to reference.
    campaign_id = f"CAMPAIGN-RETRY-{suffix}"
    db.add(OutboundCampaign(id=campaign_id, name="test", reason="REPAIR_AUTHORIZED"))
    await db.flush()
    db.add(
        CallJob(
            id=call_job_id,
            campaign_id=campaign_id,
            customer_id=customer_id,
            claim_id=claim_id,
        )
    )
    await db.commit()
    return {"customer_id": customer_id, "claim_id": claim_id}


# --- 1/15: NO_ANSWER -> retry ------------------------------------------------------------


async def test_no_answer_retries_then_reports_automated_contact_unsuccessful(
    temporal_time_skipping_env, db_session_committed
):
    seeded = await _seed_customer_claim_and_cli(
        db_session_committed, suffix="NOANS", call_job_id="JOB-NOANS"
    )

    async with Worker(
        temporal_time_skipping_env.client,
        task_queue=_TASK_QUEUE,
        workflows=_WORKFLOWS,
        activities=_ACTIVITIES,
        workflow_runner=SANDBOXED_WORKFLOW_RUNNER,
    ):
        result = await temporal_time_skipping_env.client.execute_workflow(
            RetrySchedulerWorkflow.run,
            RetrySchedulerInput(
                call_job_id="JOB-NOANS",
                customer_id=seeded["customer_id"],
                claim_id=seeded["claim_id"],
                simulated_answer_results=["NO_ANSWER", "NO_ANSWER", "NO_ANSWER"],
            ),
            id="retry-JOB-NOANS",
            task_queue=_TASK_QUEUE,
            # Generous relative to virtual time under time-skipping — up to 2 inter-attempt
            # windows of up to 6 hours each (campaigns/constants.py::ATTEMPT_WINDOWS) plus
            # buffer, not real test wall-clock time.
            execution_timeout=timedelta(hours=24),
        )

    assert result.disposition_code == DispositionCode.AUTOMATED_CONTACT_UNSUCCESSFUL.value
    assert result.attempts_made == 3

    from src.calls.models import CallAttempt

    rows = (
        (
            await db_session_committed.execute(
                select(CallAttempt).where(CallAttempt.customer_id == seeded["customer_id"])
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 3
    assert all(r.disposition_code == DispositionCode.NO_ANSWER for r in rows)


async def test_no_answer_then_answered_stops_retrying(
    temporal_time_skipping_env, db_session_committed
):
    seeded = await _seed_customer_claim_and_cli(
        db_session_committed, suffix="STOP", call_job_id="JOB-STOP"
    )

    async with Worker(
        temporal_time_skipping_env.client,
        task_queue=_TASK_QUEUE,
        workflows=_WORKFLOWS,
        activities=_ACTIVITIES,
        workflow_runner=SANDBOXED_WORKFLOW_RUNNER,
    ):
        result = await temporal_time_skipping_env.client.execute_workflow(
            RetrySchedulerWorkflow.run,
            RetrySchedulerInput(
                call_job_id="JOB-STOP",
                customer_id=seeded["customer_id"],
                claim_id=seeded["claim_id"],
                simulated_answer_results=["NO_ANSWER", "FAILED"],
            ),
            id="retry-JOB-STOP",
            task_queue=_TASK_QUEUE,
            execution_timeout=timedelta(hours=24),
        )

    # attempt 2 answers (FAILED, not NO_ANSWER/VOICEMAIL) — retry engine's job is done,
    # even though it isn't a "success."
    assert result.disposition_code == DispositionCode.NETWORK_FAILURE.value
    assert result.attempts_made == 2


# --- 14/15: CONCURRENT CALL -> AI attempt aborted ------------------------------------------


async def test_concurrent_call_conflict_aborts_without_consuming_an_attempt(
    temporal_env, db_session_committed
):
    seeded = await _seed_customer_claim_and_cli(
        db_session_committed, suffix="CONC", call_job_id="JOB-CONC"
    )

    async with Worker(
        temporal_env.client,
        task_queue=_TASK_QUEUE,
        workflows=_WORKFLOWS,
        activities=_ACTIVITIES,
        workflow_runner=SANDBOXED_WORKFLOW_RUNNER,
    ):
        # Holds the customer-keyed lock: started directly (not via the retry scheduler),
        # sits in right-party-check waiting for a signal that never comes.
        blocker = await temporal_env.client.start_workflow(
            CallSessionWorkflow.run,
            CallSessionInput(
                call_id="CALL-CONC-BLOCKER",
                customer_id=seeded["customer_id"],
                claim_id=seeded["claim_id"],
            ),
            id=f"call-session-{seeded['customer_id']}",
            task_queue=_TASK_QUEUE,
            execution_timeout=timedelta(minutes=5),
        )

        result = await temporal_env.client.execute_workflow(
            RetrySchedulerWorkflow.run,
            RetrySchedulerInput(
                call_job_id="JOB-CONC",
                customer_id=seeded["customer_id"],
                claim_id=seeded["claim_id"],
                simulated_answer_results=["HUMAN_ANSWERED"],
            ),
            id="retry-JOB-CONC",
            task_queue=_TASK_QUEUE,
            execution_timeout=timedelta(minutes=5),
        )

        await temporal_env.client.get_workflow_handle(blocker.id).terminate()

    assert result.disposition_code == DispositionCode.CONCURRENT_CALL_CONFLICT.value
    assert result.attempts_made == 0
