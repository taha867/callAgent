"""RetrySchedulerWorkflow — spec §6's no-answer/retry protocol, task 9. The outer,
long-lived workflow (`workflow_id = f"retry-{call_job_id}"`) that owns attempt timing;
CallSessionWorkflow (calls/workflows.py) is the inner, single-attempt workflow it starts as
a child for every attempt. See .claude/specs/phase-1-backend-spec.md decision 0.1.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporalio.common import WorkflowIDReusePolicy
    from temporalio.exceptions import ChildWorkflowError, WorkflowAlreadyStartedError
    from temporalio.workflow import ParentClosePolicy

    from src.actions.constants import ActionCode
    from src.calls.activities import CreateActionInput, RecordAuditEventInput
    from src.calls.activities import create_action as create_action_activity
    from src.calls.activities import record_audit_event as record_audit_event_activity
    from src.calls.constants import MAX_CALL_SESSION_SECONDS, DispositionCode
    from src.calls.schemas import CallSessionInput
    from src.calls.workflows import CallSessionWorkflow
    from src.campaigns.activities import (
        CheckEligibilityInput,
        GetStatusCriticalityInput,
        get_status_criticality_activity,
    )
    from src.campaigns.activities import check_call_eligibility as check_eligibility_activity
    from src.campaigns.constants import ATTEMPT_WINDOWS, MAX_ATTEMPTS
    from src.campaigns.schemas import RetrySchedulerInput, RetrySchedulerOutput

_ACTIVITY_TIMEOUT = timedelta(seconds=10)
_NO_ANSWER_LIKE = {DispositionCode.NO_ANSWER.value, DispositionCode.VOICEMAIL.value}


@workflow.defn
class RetrySchedulerWorkflow:
    @workflow.run
    async def run(self, inp: RetrySchedulerInput) -> RetrySchedulerOutput:
        for attempt_number in range(1, MAX_ATTEMPTS + 1):
            eligibility = await workflow.execute_activity(
                check_eligibility_activity,
                CheckEligibilityInput(customer_id=inp.customer_id, claim_id=inp.claim_id),
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )
            if not eligibility.call_eligible:
                await workflow.execute_activity(
                    record_audit_event_activity,
                    RecordAuditEventInput(
                        decision="CALL_NOT_ELIGIBLE",
                        reason_code=eligibility.ineligible_reason or "CALL_NOT_ELIGIBLE",
                        correlation_id=inp.call_job_id,
                        actor="SYSTEM",
                    ),
                    start_to_close_timeout=_ACTIVITY_TIMEOUT,
                )
                # spec §4.1/§5.1: a pre-dial ineligibility never consumes a retry attempt —
                # this attempt_number is not counted against attempts_made.
                return RetrySchedulerOutput(
                    disposition_code=eligibility.ineligible_reason or "CALL_NOT_ELIGIBLE",
                    attempts_made=attempt_number - 1,
                )

            simulated_answer_result = (
                inp.simulated_answer_results[attempt_number - 1]
                if attempt_number - 1 < len(inp.simulated_answer_results)
                else "NO_ANSWER"
            )

            try:
                result = await workflow.execute_child_workflow(
                    CallSessionWorkflow.run,
                    CallSessionInput(
                        call_id=f"{inp.call_job_id}-ATTEMPT-{attempt_number}",
                        customer_id=inp.customer_id,
                        claim_id=inp.claim_id,
                        call_job_id=inp.call_job_id,
                        attempt_number=attempt_number,
                        simulated_answer_result=simulated_answer_result,
                    ),
                    id=f"call-session-{inp.customer_id}",
                    id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
                    execution_timeout=timedelta(seconds=MAX_CALL_SESSION_SECONDS),
                    parent_close_policy=ParentClosePolicy.ABANDON,
                )
            except WorkflowAlreadyStartedError:
                return await self._finalize_concurrent_conflict(inp, attempt_number)
            except ChildWorkflowError as exc:
                if isinstance(exc.cause, WorkflowAlreadyStartedError):
                    return await self._finalize_concurrent_conflict(inp, attempt_number)
                raise

            if result.disposition_code not in _NO_ANSWER_LIKE:
                return RetrySchedulerOutput(
                    disposition_code=result.disposition_code, attempts_made=attempt_number
                )

            if attempt_number == MAX_ATTEMPTS:
                return await self._handle_attempts_exhausted(inp, attempt_number)

            window = ATTEMPT_WINDOWS[attempt_number]
            delay_seconds = window.delay_seconds(random_value=workflow.random().random())
            await workflow.sleep(timedelta(seconds=delay_seconds))

        # Unreachable — the loop above always returns by the final iteration.
        return await self._handle_attempts_exhausted(inp, MAX_ATTEMPTS)

    async def _finalize_concurrent_conflict(
        self, inp: RetrySchedulerInput, attempt_number: int
    ) -> RetrySchedulerOutput:
        await workflow.execute_activity(
            record_audit_event_activity,
            RecordAuditEventInput(
                decision="CONCURRENT_CALL_CONFLICT",
                reason_code=DispositionCode.CONCURRENT_CALL_CONFLICT.value,
                action_taken=DispositionCode.CONCURRENT_CALL_CONFLICT.value,
                correlation_id=inp.call_job_id,
                actor="SYSTEM",
            ),
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        # spec §4.1: aborted without consuming a customer retry attempt.
        return RetrySchedulerOutput(
            disposition_code=DispositionCode.CONCURRENT_CALL_CONFLICT.value,
            attempts_made=attempt_number - 1,
        )

    async def _handle_attempts_exhausted(
        self, inp: RetrySchedulerInput, attempts_made: int
    ) -> RetrySchedulerOutput:
        criticality = await workflow.execute_activity(
            get_status_criticality_activity,
            GetStatusCriticalityInput(claim_id=inp.claim_id),
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        if criticality in ("ACTION_REQUIRED", "URGENT"):
            await workflow.execute_activity(
                create_action_activity,
                CreateActionInput(
                    key=f"{inp.call_job_id}-EXHAUSTED",
                    correlation_id=inp.call_job_id,
                    claim_id=inp.claim_id,
                    action_code=ActionCode.HUMAN_CALLBACK_CREATED.value,
                    summary="Automated contact attempts exhausted for action-required status",
                ),
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        return RetrySchedulerOutput(
            disposition_code=DispositionCode.AUTOMATED_CONTACT_UNSUCCESSFUL.value,
            attempts_made=attempts_made,
        )
