"""valid_defect_log_entry — the fetch-or-404 dependency qa/router.py's {entry_id}-scoped
routes share, same shape as complaints/dependencies.py::valid_complaint.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.qa.exceptions import DefectLogEntryNotFoundError
from src.qa.models import DefectLogEntry


async def valid_defect_log_entry(
    entry_id: str, db: Annotated[AsyncSession, Depends(get_db)]
) -> DefectLogEntry:
    entry = await db.get(DefectLogEntry, entry_id)
    if entry is None:
        raise DefectLogEntryNotFoundError(entry_id)
    return entry
