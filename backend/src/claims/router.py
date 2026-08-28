"""Mock claims API — task 3, spec §27's Claims section. Every route is thin (CLAUDE.md
§2.2): validate via Depends(valid_claim), call one service function, return through
response_model. No dashboard-user auth exists yet (unscheduled — see
phase-0-frontend-spec.md decision 1); `/status` takes verification_level as an explicit
query param instead, mirroring the live-call channel's authorization model until real
ops-dashboard auth lands.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.claims import service as claims_service
from src.claims.dependencies import valid_claim
from src.claims.models import MotorClaim
from src.claims.schemas import (
    ClaimDocumentRead,
    ClaimRead,
    ClaimStatusEventRead,
    ClaimStatusRead,
    RepairGarageRead,
)
from src.database import get_db
from src.verification.constants import VerificationLevel

router = APIRouter()


@router.get("/{claim_id}", response_model=ClaimRead)
async def get_claim(claim: Annotated[MotorClaim, Depends(valid_claim)]) -> MotorClaim:
    return claim


@router.get("/{claim_id}/status", response_model=ClaimStatusRead)
async def get_claim_status(
    claim: Annotated[MotorClaim, Depends(valid_claim)],
    verification_level: Annotated[VerificationLevel, Query()] = VerificationLevel.L0,
) -> ClaimStatusRead:
    return claims_service.get_disclosable_status(claim, verification_level)


@router.get("/{claim_id}/timeline", response_model=list[ClaimStatusEventRead])
async def get_claim_timeline(
    claim: Annotated[MotorClaim, Depends(valid_claim)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ClaimStatusEventRead]:
    events = await claims_service.get_claim_timeline(db, claim.id)
    return [ClaimStatusEventRead.model_validate(e) for e in events]


@router.get("/{claim_id}/documents", response_model=list[ClaimDocumentRead])
async def get_claim_documents(
    claim: Annotated[MotorClaim, Depends(valid_claim)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ClaimDocumentRead]:
    documents = await claims_service.get_claim_documents(db, claim.id)
    return [ClaimDocumentRead.model_validate(d) for d in documents]


@router.get("/{claim_id}/garage", response_model=RepairGarageRead | None)
async def get_claim_garage(
    claim: Annotated[MotorClaim, Depends(valid_claim)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RepairGarageRead | None:
    garage = await claims_service.get_garage_for_claim(db, claim)
    return RepairGarageRead.model_validate(garage) if garage is not None else None
