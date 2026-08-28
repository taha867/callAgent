"""create_action(), create_escalation(), schedule_callback() — task 7, all idempotent via
src/idempotency.py::idempotent() (spec §10.6.4/§36 rule 27). Per that module's own
docstring, `idempotent()` commits `session` itself — callers here must not (and do not)
wrap these calls in an outer `async with session.begin():`.
"""

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.actions.constants import ActionCode
from src.actions.models import Callback, ClaimAction, Escalation
from src.idempotency import idempotent


async def create_action(
    session: AsyncSession,
    *,
    key: str,
    correlation_id: str,
    claim_id: str,
    action_code: ActionCode,
    summary: str,
    source_call_id: str | None = None,
) -> dict[str, Any]:
    async def _operation() -> dict[str, Any]:
        action = ClaimAction(
            claim_id=claim_id,
            action_code=action_code,
            summary=summary,
            source_call_id=source_call_id,
        )
        session.add(action)
        await session.flush()
        return {
            "id": action.id,
            "claim_id": action.claim_id,
            "action_code": action.action_code.value,
            "summary": action.summary,
            "status": action.status,
            "created_at": action.created_at.isoformat(),
        }

    return await idempotent(
        session,
        key=key,
        correlation_id=correlation_id,
        operation_name="create_action",
        payload={"claim_id": claim_id, "action_code": action_code.value, "summary": summary},
        operation=_operation,
    )


async def send_secure_link(
    session: AsyncSession,
    *,
    key: str,
    correlation_id: str,
    claim_id: str,
    customer_id: str,
    link_type: str,
    source_call_id: str | None = None,
) -> dict[str, Any]:
    """Phase 2's send_secure_link tool (voice/tools.py) — modeled as a ClaimAction, same
    idempotent-write shape as create_action/schedule_callback. No real SMS/email vendor
    exists at this phase (same reasoning as verification/adapters/otp_delivery's
    "log_only" adapter) — the link itself is never generated or delivered here; this
    persists that an approved secure link *should* be sent, for a human/later-phase
    delivery-vendor integration to act on."""

    async def _operation() -> dict[str, Any]:
        action = ClaimAction(
            claim_id=claim_id,
            action_code=ActionCode.DOCUMENT_SUBMISSION_LINK_REQUEST,
            summary=f"Secure link requested for customer {customer_id}: {link_type}",
            source_call_id=source_call_id,
        )
        session.add(action)
        await session.flush()
        return {
            "id": action.id,
            "claim_id": action.claim_id,
            "customer_id": customer_id,
            "link_type": link_type,
            "action_code": action.action_code.value,
            "status": action.status,
            "created_at": action.created_at.isoformat(),
        }

    return await idempotent(
        session,
        key=key,
        correlation_id=correlation_id,
        operation_name="send_secure_link",
        payload={"claim_id": claim_id, "customer_id": customer_id, "link_type": link_type},
        operation=_operation,
    )


async def create_escalation(
    session: AsyncSession,
    *,
    key: str,
    correlation_id: str,
    call_id: str,
    reason: str,
    context_snapshot: dict[str, Any],
) -> dict[str, Any]:
    async def _operation() -> dict[str, Any]:
        escalation = Escalation(call_id=call_id, reason=reason, context_snapshot=context_snapshot)
        session.add(escalation)
        await session.flush()
        return {
            "id": escalation.id,
            "call_id": escalation.call_id,
            "reason": escalation.reason,
            "status": escalation.status,
            "created_at": escalation.created_at.isoformat(),
        }

    return await idempotent(
        session,
        key=key,
        correlation_id=correlation_id,
        operation_name="create_escalation",
        payload={"call_id": call_id, "reason": reason},
        operation=_operation,
    )


async def schedule_callback(
    session: AsyncSession,
    *,
    key: str,
    correlation_id: str,
    customer_id: str,
    callback_window_start: datetime,
    callback_window_end: datetime,
    reason: str,
    claim_id: str | None = None,
) -> dict[str, Any]:
    async def _operation() -> dict[str, Any]:
        callback = Callback(
            customer_id=customer_id,
            claim_id=claim_id,
            callback_window_start=callback_window_start,
            callback_window_end=callback_window_end,
            reason=reason,
        )
        session.add(callback)
        await session.flush()
        return {
            "id": callback.id,
            "customer_id": callback.customer_id,
            "claim_id": callback.claim_id,
            "callback_window_start": callback.callback_window_start.isoformat(),
            "callback_window_end": callback.callback_window_end.isoformat(),
            "reason": callback.reason,
            "status": callback.status,
        }

    return await idempotent(
        session,
        key=key,
        correlation_id=correlation_id,
        operation_name="schedule_callback",
        payload={
            "customer_id": customer_id,
            "claim_id": claim_id,
            "callback_window_start": callback_window_start.isoformat(),
            "callback_window_end": callback_window_end.isoformat(),
            "reason": reason,
        },
        operation=_operation,
    )
