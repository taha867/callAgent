"""AdversarialScenarioId.CONTACT_WINDOW_BLACKOUT — spec §6.1's Ramadan/holiday blackout
window. telephony/service.py::is_within_contact_window() and BusinessContactCalendar
already existed as a stub with zero seeded rows (every date resolved "open"); Phase 4 adds
two synthetic demo-only rows (scripts/seed_demo_data.py) so this mechanism is finally
exercisable. Uses `seeded_db` (runs scripts/seed_demo_data.py against the test DB) rather
than db_session_committed directly.
"""

from datetime import datetime

from src.telephony import service as telephony_service


async def test_blackout_date_rejects_the_contact_window(seeded_db):
    at = datetime(2026, 9, 6, 10, 0, 0)  # seeded BLACKOUT row
    assert await telephony_service.is_within_contact_window(seeded_db, at) is False


async def test_ramadan_row_rejects_the_contact_window(seeded_db):
    at = datetime(2026, 9, 5, 10, 0, 0)  # seeded RAMADAN row
    assert await telephony_service.is_within_contact_window(seeded_db, at) is False


async def test_an_unseeded_date_leaves_the_normal_contact_window_open(seeded_db):
    at = datetime(2026, 9, 10, 10, 0, 0)  # no calendar row for this date
    assert await telephony_service.is_within_contact_window(seeded_db, at) is True
