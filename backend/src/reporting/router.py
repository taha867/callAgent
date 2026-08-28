"""6 read-only GET endpoints, one per spec §31 subsection + escalation-analytics (the phase
file's own "attempt/escalation analytics views" line item — attempt analytics folds into
no-answer-analytics, since spec §31 itself lists "attempt number vs answer rate" under that
section rather than as its own; escalation-analytics has no spec §31 subsection at all, so
its shape here is this implementation's own design, not a literal spec quote).

`since`/`until` are required, never defaulted — an implicit "last 24h" would silently hide
a stale/empty range from whoever's querying. No auth dependency — src/auth/ doesn't exist
yet, consistent with every other route in this codebase today.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.reporting import service as reporting_service
from src.reporting.schemas import (
    CustomerExperienceRead,
    EscalationAnalyticsRead,
    NoAnswerAnalyticsRead,
    OperationsOverviewRead,
    OutcomeFunnelRead,
    StatusAnalyticsRow,
)

router = APIRouter()

DateRange = tuple[datetime, datetime]


async def get_range(since: datetime, until: datetime) -> DateRange:
    """FastAPI/Pydantic parses a Z-suffixed ISO query param (what every frontend caller
    sends, per .claude/specs/phase-3-frontend-spec.md §0.3's encodeURIComponent'd
    .toISOString() values) into a timezone-AWARE datetime. Every DateTime column in this
    codebase is naive TIMESTAMP WITHOUT TIME ZONE (the Phase 0 convention —
    calls/workflows.py::_now() strips tzinfo for the identical reason) — binding a
    tz-aware datetime against one raises asyncpg.DataError ("can't subtract offset-naive
    and offset-aware datetimes"). Strip tzinfo here, once, as a shared dependency rather
    than repeating it in all six route bodies below."""
    return since.replace(tzinfo=None), until.replace(tzinfo=None)


@router.get("/operations-overview", response_model=OperationsOverviewRead)
async def operations_overview(
    date_range: Annotated[DateRange, Depends(get_range)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OperationsOverviewRead:
    since, until = date_range
    return await reporting_service.get_operations_overview(db, since=since, until=until)


@router.get("/outcome-funnel", response_model=OutcomeFunnelRead)
async def outcome_funnel(
    date_range: Annotated[DateRange, Depends(get_range)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OutcomeFunnelRead:
    since, until = date_range
    return await reporting_service.get_outcome_funnel(db, since=since, until=until)


@router.get("/no-answer-analytics", response_model=NoAnswerAnalyticsRead)
async def no_answer_analytics(
    date_range: Annotated[DateRange, Depends(get_range)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NoAnswerAnalyticsRead:
    since, until = date_range
    return await reporting_service.get_no_answer_analytics(db, since=since, until=until)


@router.get("/status-analytics", response_model=list[StatusAnalyticsRow])
async def status_analytics(
    date_range: Annotated[DateRange, Depends(get_range)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[StatusAnalyticsRow]:
    since, until = date_range
    return await reporting_service.get_status_analytics(db, since=since, until=until)


@router.get("/customer-experience", response_model=CustomerExperienceRead)
async def customer_experience(
    date_range: Annotated[DateRange, Depends(get_range)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CustomerExperienceRead:
    since, until = date_range
    return await reporting_service.get_customer_experience(db, since=since, until=until)


@router.get("/escalation-analytics", response_model=EscalationAnalyticsRead)
async def escalation_analytics(
    date_range: Annotated[DateRange, Depends(get_range)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EscalationAnalyticsRead:
    since, until = date_range
    return await reporting_service.get_escalation_analytics(db, since=since, until=until)
