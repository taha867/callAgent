"""POST /claims/{claimId}/actions, POST /claims/{claimId}/escalations — spec §27's Actions
section. Both are idempotent (spec §10.6.4) via the `Idempotency-Key` request header,
matching spec's own example verbatim (`Idempotency-Key: CALL-88120-ACTION-004`) — the
dashboard/API caller mints the key, same as calls/workflows.py mints one per action it
creates during a live call.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.actions import service as actions_service
from src.actions.schemas import ActionCreate, ActionRead, EscalationCreate, EscalationRead
from src.claims.dependencies import valid_claim
from src.claims.models import MotorClaim
from src.database import get_db

router = APIRouter()


@router.post("/{claim_id}/actions", response_model=ActionRead)
async def create_action(
    claim: Annotated[MotorClaim, Depends(valid_claim)],
    body: ActionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str, Header()],
) -> ActionRead:
    result = await actions_service.create_action(
        db,
        key=idempotency_key,
        correlation_id=claim.id,
        claim_id=claim.id,
        action_code=body.action_code,
        summary=body.summary,
        source_call_id=body.source_call_id,
    )
    return ActionRead(**result)


@router.post("/{claim_id}/escalations", response_model=EscalationRead)
async def create_escalation(
    claim: Annotated[MotorClaim, Depends(valid_claim)],
    body: EscalationCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str, Header()],
) -> EscalationRead:
    result = await actions_service.create_escalation(
        db,
        key=idempotency_key,
        correlation_id=claim.id,
        call_id=body.call_id,
        reason=body.reason,
        context_snapshot=body.context_snapshot,
    )
    return EscalationRead(**result)
