"""qa/ domain service — no idempotency wrapper, no kill-switch check
(.claude/specs/phase-4-backend-spec.md §0.8): every write here is dev-process metadata
about a past call/test outcome, never a decision that originates or continues a live call.

`compilation_required()` is the pure function both `to_read()` (API serialization) and
scripts/ci/check_defect_log_two_strike.py (the two-strike CI gate) call — one place decides
what "needs compiling" means.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.pagination import Page, PaginationParams
from src.qa.constants import DefectStatus
from src.qa.exceptions import DefectShapeKeyNotFoundError
from src.qa.models import DefectLogEntry, JourneyRunResult
from src.qa.schemas import (
    DefectLogEntryCreate,
    DefectLogEntryRead,
    DefectLogEntryUpdate,
    DefectOccurrenceCreate,
    GovernanceSummary,
    JourneyRunCreate,
    JourneyRunRead,
)


def compilation_required(entry: DefectLogEntry) -> bool:
    return entry.occurrence_count >= 2 and entry.status != DefectStatus.COMPILED


def to_read(entry: DefectLogEntry) -> DefectLogEntryRead:
    return DefectLogEntryRead(
        id=entry.id,
        title=entry.title,
        defect_shape_key=entry.defect_shape_key,
        demo_journey_id=entry.demo_journey_id,
        adversarial_scenario_id=entry.adversarial_scenario_id,
        language=entry.language,
        severity=entry.severity,
        notes=entry.notes,
        status=entry.status,
        occurrence_count=entry.occurrence_count,
        compiled_artifact_type=entry.compiled_artifact_type,
        compiled_artifact_ref=entry.compiled_artifact_ref,
        first_seen_at=entry.first_seen_at,
        last_seen_at=entry.last_seen_at,
        compilation_required=compilation_required(entry),
    )


async def create_defect(db: AsyncSession, payload: DefectLogEntryCreate) -> DefectLogEntryRead:
    now = datetime.now(UTC).replace(tzinfo=None)
    entry = DefectLogEntry(
        title=payload.title,
        defect_shape_key=payload.defect_shape_key,
        demo_journey_id=payload.demo_journey_id,
        adversarial_scenario_id=payload.adversarial_scenario_id,
        language=payload.language,
        severity=payload.severity,
        notes=payload.notes,
        occurrence_count=1,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(entry)
    await db.flush()
    return to_read(entry)


async def list_defects(
    db: AsyncSession,
    *,
    status: str | None,
    demo_journey_id: str | None,
    params: PaginationParams,
) -> Page[DefectLogEntryRead]:
    filters = []
    if status is not None:
        filters.append(DefectLogEntry.status == status)
    if demo_journey_id is not None:
        filters.append(DefectLogEntry.demo_journey_id == demo_journey_id)

    total = (
        await db.execute(select(func.count()).select_from(DefectLogEntry).where(*filters))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                select(DefectLogEntry)
                .where(*filters)
                .order_by(DefectLogEntry.last_seen_at.desc())
                .limit(params.page_size)
                .offset(params.offset)
            )
        )
        .scalars()
        .all()
    )
    return Page.create(items=[to_read(r) for r in rows], total=total, params=params)


async def list_all_defects(db: AsyncSession) -> list[DefectLogEntry]:
    """Unpaginated — used only by scripts/ci/check_defect_log_two_strike.py, which needs
    every row to check the two-strike rule, not a page of them."""
    return list((await db.execute(select(DefectLogEntry))).scalars().all())


async def get_by_shape_key(db: AsyncSession, shape_key: str) -> DefectLogEntry | None:
    return (
        await db.execute(select(DefectLogEntry).where(DefectLogEntry.defect_shape_key == shape_key))
    ).scalars().first()


async def record_occurrence(
    db: AsyncSession, shape_key: str, payload: DefectOccurrenceCreate
) -> DefectLogEntryRead:
    entry = await get_by_shape_key(db, shape_key)
    if entry is None:
        raise DefectShapeKeyNotFoundError(shape_key)
    entry.occurrence_count += 1
    entry.last_seen_at = datetime.now(UTC).replace(tzinfo=None)
    if payload.notes:
        entry.notes = f"{entry.notes or ''}\n[occurrence {entry.occurrence_count}] {payload.notes}".strip()
    await db.flush()
    return to_read(entry)


async def update_status(
    db: AsyncSession, entry: DefectLogEntry, payload: DefectLogEntryUpdate
) -> DefectLogEntryRead:
    updates: dict[str, Any] = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(entry, field, value)
    await db.flush()
    return to_read(entry)


async def record_journey_run(db: AsyncSession, payload: JourneyRunCreate) -> JourneyRunRead:
    run = JourneyRunResult(
        demo_journey_id=payload.demo_journey_id,
        adversarial_scenario_id=payload.adversarial_scenario_id,
        passed=payload.passed,
        run_at=datetime.now(UTC).replace(tzinfo=None),
        defect_log_entry_id=payload.defect_log_entry_id,
        test_node_id=payload.test_node_id,
    )
    db.add(run)
    await db.flush()
    return JourneyRunRead.model_validate(run)


async def list_journey_runs(
    db: AsyncSession, *, demo_journey_id: str | None = None, latest_only: bool = False
) -> list[JourneyRunRead]:
    filters = []
    if demo_journey_id is not None:
        filters.append(JourneyRunResult.demo_journey_id == demo_journey_id)

    rows = (
        (
            await db.execute(
                select(JourneyRunResult).where(*filters).order_by(JourneyRunResult.run_at.desc())
            )
        )
        .scalars()
        .all()
    )

    if not latest_only:
        return [JourneyRunRead.model_validate(r) for r in rows]

    # Latest cooperative (adversarial_scenario_id is None) run per demo_journey_id — the
    # dashboard's "is this journey currently passing" view (phase-4-frontend-spec.md §3.2).
    latest_by_journey: dict[str, JourneyRunResult] = {}
    for row in rows:  # already ordered newest-first
        if row.adversarial_scenario_id is not None:
            continue
        latest_by_journey.setdefault(row.demo_journey_id, row)
    return [JourneyRunRead.model_validate(r) for r in latest_by_journey.values()]


async def governance_summary(db: AsyncSession) -> GovernanceSummary:
    entries = await list_all_defects(db)
    total_defects = len(entries)
    open_defects = sum(1 for e in entries if e.status == DefectStatus.OPEN)
    compilation_required_count = sum(1 for e in entries if compilation_required(e))

    latest_runs = await list_journey_runs(db, latest_only=True)
    journeys_passing = sum(1 for r in latest_runs if r.passed)

    return GovernanceSummary(
        total_defects=total_defects,
        open_defects=open_defects,
        compilation_required_count=compilation_required_count,
        journeys_passing=journeys_passing,
    )
