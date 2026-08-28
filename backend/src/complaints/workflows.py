"""ComplaintSlaMonitorWorkflow — durable timers for spec §18.1's acknowledgment/resolution
SLA clock, task 7. Started by CallSessionWorkflow's COMPLAINT_REQUEST branch right after
create_complaint's activity commits the Complaint row — as an ABANDON-policy CHILD workflow
(`id=f"complaint-sla-{complaint_id}"`), not a plain child: ABANDON is what lets it keep
running long after the parent CallSessionWorkflow itself completes (spec §18.1's clock
outlives the call), while still starting from inside the same, already-correct Temporal
environment the parent is running in — avoiding an activity independently reconnecting a
Temporal client, which risks pointing at the wrong server under a time-skipping test
environment. See CLAUDE.md §2.6 and .claude/specs/phase-1-backend-spec.md §8.2.
"""

from datetime import datetime, timedelta

from pydantic import BaseModel
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from src.actions.constants import ActionCode
    from src.calls.activities import CreateActionInput
    from src.calls.activities import create_action as create_action_activity
    from src.complaints.activities import (
        IsDeadlineClearedInput,
        RaiseComplaintSlaEventInput,
    )
    from src.complaints.activities import is_deadline_cleared as is_deadline_cleared_activity
    from src.complaints.activities import (
        raise_complaint_sla_event as raise_complaint_sla_event_activity,
    )

_ACTIVITY_TIMEOUT = timedelta(seconds=10)
_WARNING_HOURS_DEFAULT = 4  # mirrors complaints/config.py::ComplaintsConfig.SLA_WARNING_HOURS


def _now() -> datetime:
    return workflow.now().replace(tzinfo=None)


class ComplaintSlaMonitorInput(BaseModel):
    complaint_id: str
    claim_id: str
    acknowledgment_due_at: datetime
    resolution_due_at: datetime
    warning_hours: int = _WARNING_HOURS_DEFAULT


@workflow.defn
class ComplaintSlaMonitorWorkflow:
    @workflow.run
    async def run(self, inp: ComplaintSlaMonitorInput) -> None:
        for deadline_kind, due_at in (
            ("ACKNOWLEDGMENT", inp.acknowledgment_due_at),
            ("RESOLUTION", inp.resolution_due_at),
        ):
            await self._wait_and_check(
                inp, deadline_kind, due_at - timedelta(hours=inp.warning_hours), "AT_RISK"
            )
            await self._wait_and_check(inp, deadline_kind, due_at, "BREACHED")

    async def _wait_and_check(
        self,
        inp: ComplaintSlaMonitorInput,
        deadline_kind: str,
        target_at: datetime,
        event_type: str,
    ) -> None:
        remaining = target_at - _now()
        if remaining.total_seconds() > 0:
            await workflow.sleep(remaining)

        cleared = await workflow.execute_activity(
            is_deadline_cleared_activity,
            IsDeadlineClearedInput(complaint_id=inp.complaint_id, deadline_kind=deadline_kind),
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        if cleared:
            return

        await workflow.execute_activity(
            raise_complaint_sla_event_activity,
            RaiseComplaintSlaEventInput(
                complaint_id=inp.complaint_id, event_type=event_type, deadline_kind=deadline_kind
            ),
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        await workflow.execute_activity(
            create_action_activity,
            CreateActionInput(
                key=f"{inp.complaint_id}-SLA-{deadline_kind}-{event_type}",
                correlation_id=inp.complaint_id,
                claim_id=inp.claim_id,
                action_code=ActionCode.COMPLAINT_SLA_ESCALATION.value,
                summary=f"Complaint {inp.complaint_id} SLA {deadline_kind} {event_type.lower()}",
            ),
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
