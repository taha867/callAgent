"""privacy/service.py::record_redaction_events() — the idempotency non-negotiable
(CLAUDE.md §4), mechanically checked: two calls with the identical (call_id, turn_index)
key must produce exactly one PiiRedactionEvent row per category, not a duplicate.
"""

from sqlalchemy import select

from src.privacy.constants import PiiCategory
from src.privacy.models import PiiRedactionEvent
from src.privacy.service import record_redaction_events


async def _count_events(db_session, call_id: str) -> int:
    result = await db_session.execute(
        select(PiiRedactionEvent).where(PiiRedactionEvent.call_id == call_id)
    )
    return len(result.scalars().all())


async def test_duplicate_call_produces_one_row_per_category(db_session):
    call_id = "CALL-IDEMP-1"
    detections = [PiiCategory.EMIRATES_ID, PiiCategory.OTP_PIN_CVV_PASSWORD]

    await record_redaction_events(db_session, call_id=call_id, turn_index=0, detections=detections)
    await record_redaction_events(db_session, call_id=call_id, turn_index=0, detections=detections)

    assert await _count_events(db_session, call_id) == 2  # not 4


async def test_zero_detections_writes_nothing(db_session):
    call_id = "CALL-IDEMP-2"
    await record_redaction_events(db_session, call_id=call_id, turn_index=0, detections=[])
    assert await _count_events(db_session, call_id) == 0


async def test_different_turns_write_independently(db_session):
    call_id = "CALL-IDEMP-3"
    await record_redaction_events(
        db_session, call_id=call_id, turn_index=0, detections=[PiiCategory.IBAN]
    )
    await record_redaction_events(
        db_session, call_id=call_id, turn_index=1, detections=[PiiCategory.IBAN]
    )
    assert await _count_events(db_session, call_id) == 2
