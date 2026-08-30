"""POST/GET/PATCH /qa/defect-log, POST /qa/defect-log/{shape_key}/occurrences,
POST/GET /qa/journey-runs, GET /qa/governance-summary —
.claude/specs/phase-4-backend-spec.md §4.

No Depends(require_outbound_enabled), no idempotency wrapper — see that spec's §0.8: this
domain never originates or continues a live call.

Every mutating route commits explicitly with `await db.commit()` AFTER calling the service
function, rather than wrapping the call in `async with db.begin():` — SQLAlchemy's
AsyncSession autobegins a transaction on first use, so a route whose entry comes from
Depends(valid_defect_log_entry) (which already queries the session) would hit
"a transaction is already begun on this Session" if it also tried an explicit `db.begin()`
block. `db.commit()` is safe either way — it commits whatever transaction is already open,
autobegun or not — so this one pattern is used uniformly across every write here.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.pagination import Page, PaginationParams, pagination_params
from src.qa import service
from src.qa.dependencies import valid_defect_log_entry
from src.qa.models import DefectLogEntry
from src.qa.schemas import (
    DefectLogEntryCreate,
    DefectLogEntryRead,
    DefectLogEntryUpdate,
    DefectOccurrenceCreate,
    GovernanceSummary,
    JourneyRunCreate,
    JourneyRunRead,
)

router = APIRouter()


@router.post("/defect-log", response_model=DefectLogEntryRead)
async def create_defect(
    payload: DefectLogEntryCreate, db: Annotated[AsyncSession, Depends(get_db)]
) -> DefectLogEntryRead:
    result = await service.create_defect(db, payload)
    await db.commit()
    return result


@router.get("/defect-log", response_model=Page[DefectLogEntryRead])
async def list_defects(
    db: Annotated[AsyncSession, Depends(get_db)],
    params: Annotated[PaginationParams, Depends(pagination_params)],
    status: str | None = None,
    demo_journey_id: str | None = None,
) -> Page[DefectLogEntryRead]:
    return await service.list_defects(
        db, status=status, demo_journey_id=demo_journey_id, params=params
    )


@router.get("/defect-log/{entry_id}", response_model=DefectLogEntryRead)
async def get_defect(
    entry: Annotated[DefectLogEntry, Depends(valid_defect_log_entry)]
) -> DefectLogEntryRead:
    return service.to_read(entry)


@router.patch("/defect-log/{entry_id}", response_model=DefectLogEntryRead)
async def update_defect_status(
    payload: DefectLogEntryUpdate,
    entry: Annotated[DefectLogEntry, Depends(valid_defect_log_entry)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DefectLogEntryRead:
    result = await service.update_status(db, entry, payload)
    await db.commit()
    return result


@router.post("/defect-log/{shape_key}/occurrences", response_model=DefectLogEntryRead)
async def record_occurrence(
    shape_key: str,
    payload: DefectOccurrenceCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DefectLogEntryRead:
    result = await service.record_occurrence(db, shape_key, payload)
    await db.commit()
    return result


@router.post("/journey-runs", response_model=JourneyRunRead)
async def create_journey_run(
    payload: JourneyRunCreate, db: Annotated[AsyncSession, Depends(get_db)]
) -> JourneyRunRead:
    result = await service.record_journey_run(db, payload)
    await db.commit()
    return result


@router.get("/journey-runs", response_model=list[JourneyRunRead])
async def list_journey_runs(
    db: Annotated[AsyncSession, Depends(get_db)], demo_journey_id: str | None = None
) -> list[JourneyRunRead]:
    return await service.list_journey_runs(db, demo_journey_id=demo_journey_id)


@router.get("/governance-summary", response_model=GovernanceSummary)
async def get_governance_summary(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> GovernanceSummary:
    return await service.governance_summary(db)
