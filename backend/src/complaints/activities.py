"""is_deadline_cleared, raise_complaint_sla_event — ComplaintSlaMonitorWorkflow's own
activities, task 7/§18.1. create_action (COMPLAINT_SLA_ESCALATION) is reused directly from
calls/activities.py rather than duplicated here.

Phase 1 has no endpoint that transitions Complaint.status past "OPEN" (spec §18: "complaint
resolution remains human-controlled for the MVP," and no dashboard exists yet) — so
is_deadline_cleared will, in practice, always report False for every complaint created in
this phase. That's expected: nothing acknowledges/resolves a complaint yet, so every SLA
deadline this phase creates genuinely is at risk / breached. The mechanism is what this
phase proves; a real acknowledgment/resolution flow is a later phase's dashboard feature.
"""

from pydantic import BaseModel
from temporalio import activity

from src.complaints.models import Complaint, ComplaintSlaEvent
from src.database import get_session_factory


class IsDeadlineClearedInput(BaseModel):
    complaint_id: str
    deadline_kind: str  # "ACKNOWLEDGMENT" | "RESOLUTION"


@activity.defn(name="is_deadline_cleared")
async def is_deadline_cleared(inp: IsDeadlineClearedInput) -> bool:
    session_factory = get_session_factory()
    async with session_factory() as session:
        complaint = await session.get(Complaint, inp.complaint_id)
        if complaint is None:
            return True  # nothing to warn about — treat as cleared, not a false alarm
        if inp.deadline_kind == "ACKNOWLEDGMENT":
            return complaint.status != "OPEN"
        return complaint.status == "RESOLVED"


class RaiseComplaintSlaEventInput(BaseModel):
    complaint_id: str
    event_type: str  # "AT_RISK" | "BREACHED"
    deadline_kind: str


@activity.defn(name="raise_complaint_sla_event")
async def raise_complaint_sla_event(inp: RaiseComplaintSlaEventInput) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        session.add(
            ComplaintSlaEvent(
                complaint_id=inp.complaint_id,
                event_type=inp.event_type,
                deadline_kind=inp.deadline_kind,
            )
        )


ALL_COMPLAINTS_ACTIVITIES = [is_deadline_cleared, raise_complaint_sla_event]
