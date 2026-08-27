"""record_audit_event — production code (used by every later phase's workflows, not just
the Phase 0 smoke test). Opens its own session via get_session_factory() rather than
Depends(get_db()), since activities never run inside a FastAPI request.
"""

from typing import Any, Literal

from pydantic import BaseModel
from temporalio import activity

from src.audit import service as audit_service
from src.database import get_session_factory


class RecordAuditEventInput(BaseModel):
    decision: str
    reason_code: str
    policy_rule: str | None = None
    action_taken: str | None = None
    call_id: str | None = None
    correlation_id: str | None = None
    actor: Literal["SYSTEM", "AI", "HUMAN"] = "SYSTEM"
    metadata: dict[str, Any] | None = None


@activity.defn(name="record_audit_event")
async def record_audit_event(inp: RecordAuditEventInput) -> str:
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        event = await audit_service.record_event(
            session,
            decision=inp.decision,
            reason_code=inp.reason_code,
            policy_rule=inp.policy_rule,
            action_taken=inp.action_taken,
            call_id=inp.call_id,
            correlation_id=inp.correlation_id,
            actor=inp.actor,
            metadata=inp.metadata,
        )
        event_id = event.id
    return event_id
