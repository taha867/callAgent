"""valid_claim — the fetch-or-404 dependency every claims/router.py route reuses, per
CLAUDE.md §2.2's valid_call_session pattern."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.claims import service as claims_service
from src.claims.exceptions import ClaimNotFoundError
from src.claims.models import MotorClaim
from src.database import get_db


async def valid_claim(claim_id: str, db: Annotated[AsyncSession, Depends(get_db)]) -> MotorClaim:
    claim = await claims_service.get_claim(db, claim_id)
    if claim is None:
        raise ClaimNotFoundError(claim_id)
    return claim
