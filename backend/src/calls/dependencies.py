"""valid_call_attempt — the fetch-or-404 dependency calls/router.py's routes share,
mirroring claims/dependencies.py::valid_claim's pattern (CLAUDE.md §2.2)."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.calls.exceptions import CallAttemptNotFoundError
from src.calls.models import CallAttempt
from src.database import get_db


async def valid_call_attempt(
    call_id: str, db: Annotated[AsyncSession, Depends(get_db)]
) -> CallAttempt:
    attempt = await db.get(CallAttempt, call_id)
    if attempt is None:
        raise CallAttemptNotFoundError(call_id)
    return attempt
