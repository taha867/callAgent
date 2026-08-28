"""valid_complaint — the fetch-or-404 dependency complaints/router.py's routes share."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.complaints.exceptions import ComplaintNotFoundError
from src.complaints.models import Complaint
from src.database import get_db


async def valid_complaint(
    complaint_id: str, db: Annotated[AsyncSession, Depends(get_db)]
) -> Complaint:
    complaint = await db.get(Complaint, complaint_id)
    if complaint is None:
        raise ComplaintNotFoundError(complaint_id)
    return complaint
