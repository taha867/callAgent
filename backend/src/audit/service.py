"""The ONLY public callable this module exports is `record_event`. That is deliberate and
load-bearing (see src/audit/models.py's module docstring, layer 1 of 3) — do not add an
update/delete/patch function here; if a use case ever seems to need one, the correct
answer is a new AuditEvent row explaining the correction, never a mutation of the old one.
"""

from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from src.audit.models import AuditEvent
from src.audit.schemas import AuditEventCreate

__all__ = ["record_event"]


async def record_event(
    session: AsyncSession,
    *,
    decision: str,
    reason_code: str,
    policy_rule: str | None = None,
    action_taken: str | None = None,
    call_id: str | None = None,
    correlation_id: str | None = None,
    actor: Literal["SYSTEM", "AI", "HUMAN"] = "SYSTEM",
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    validated = AuditEventCreate(
        decision=decision,
        reason_code=reason_code,
        policy_rule=policy_rule,
        action_taken=action_taken,
        call_id=call_id,
        correlation_id=correlation_id,
        actor=actor,
        metadata=metadata,
    )
    event = AuditEvent(
        decision=validated.decision,
        reason_code=validated.reason_code,
        policy_rule=validated.policy_rule,
        action_taken=validated.action_taken,
        call_id=validated.call_id,
        correlation_id=validated.correlation_id,
        actor=validated.actor,
        metadata_json=validated.metadata,
    )
    session.add(event)
    await session.flush()  # caller owns the transaction/commit
    return event
