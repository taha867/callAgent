"""validate_cli(), is_within_contact_window() — spec §4.1/§6.1, task 4's "CLI validation
stub, contact-calendar stub." Plain async functions over an AsyncSession, no Temporal
awareness — callers (campaigns/activities.py) decide what "now" means, per
.claude/specs/phase-1-backend-implementation-plan.md's correction §3: this module never
reads workflow.now() or datetime.now() itself.
"""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.telephony.models import BusinessContactCalendar, TelephonyCliConfiguration


async def get_active_cli(session: AsyncSession) -> TelephonyCliConfiguration | None:
    """The single active, trunk-authorized CLI configured for outbound dialing. Returns
    None if none is configured/active — the caller treats that as ineligible, spec §4.1's
    INVALID_OR_UNAUTHORIZED_CLI."""
    result = await session.execute(
        select(TelephonyCliConfiguration).where(
            TelephonyCliConfiguration.is_active.is_(True),
            TelephonyCliConfiguration.trunk_authorized.is_(True),
        )
    )
    return result.scalars().first()


async def validate_cli(session: AsyncSession, cli: str) -> bool:
    """True only if `cli` matches an active, trunk-authorized configuration row."""
    result = await session.execute(
        select(TelephonyCliConfiguration).where(
            TelephonyCliConfiguration.cli == cli,
            TelephonyCliConfiguration.is_active.is_(True),
            TelephonyCliConfiguration.trunk_authorized.is_(True),
        )
    )
    return result.scalars().first() is not None


async def is_within_contact_window(session: AsyncSession, at: datetime) -> bool:
    """True unless an active BusinessContactCalendar row for `at.date()` sets
    contact_allowed=False. Stub per task 4: with no seeded blackout rows, every date is
    open — real Ramadan/holiday data lands in Phase 5."""
    contact_date: date = at.date()
    result = await session.execute(
        select(BusinessContactCalendar).where(BusinessContactCalendar.calendar_date == contact_date)
    )
    rows = result.scalars().all()
    if not rows:
        return True  # no exceptional-day row for this date — normal contact window applies
    return all(row.contact_allowed for row in rows)
