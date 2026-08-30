"""AdversarialScenarioId.IDEMPOTENCY_REPLAY — merges two raw checklist bullets ("Backend
action committed but response lost (idempotency replay)" and "Repeated action retry with the
same idempotency key") into one canonical scenario, since both exercise the same mechanism
(src/idempotency.py::idempotent) from two angles: a same-key/same-payload retry must replay
the original result without a duplicate write, and a same-key/different-payload retry must
be rejected outright (spec §36 rule 27).
"""

from datetime import UTC, datetime

from sqlalchemy import select

from src.complaints import service as complaints_service
from src.complaints.config import ComplaintsConfig
from src.complaints.models import Complaint
from src.exceptions import IdempotencyKeyReuseError
from tests.scripted_conversations.conftest import _seed_customer_and_claim


async def test_same_key_same_payload_replays_without_a_duplicate_row(db_session_committed):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="IDEMP1")
    key = "IDEMP-TEST-REPLAY-1"
    now = datetime.now(UTC).replace(tzinfo=None)
    kwargs = {
        "key": key,
        "correlation_id": "CALL-IDEMP-1",
        "claim_id": seeded["claim_id"],
        "source_call_id": "CALL-IDEMP-1",
        "complaint_category": "REPAIR_QUALITY",
        "customer_statement_summary": "The repair work is substandard",
        "severity": "HIGH",
        "preferred_contact_method": "PHONE",
        "now": now,
        "config": ComplaintsConfig(),
    }

    first = await complaints_service.create_complaint(db_session_committed, **kwargs)
    second = await complaints_service.create_complaint(db_session_committed, **kwargs)

    assert first == second  # identical replayed response, not a fresh row

    rows = (
        (
            await db_session_committed.execute(
                select(Complaint).where(Complaint.source_call_id == "CALL-IDEMP-1")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1  # never duplicated


async def test_same_key_different_payload_is_rejected(db_session_committed):
    seeded = await _seed_customer_and_claim(db_session_committed, suffix="IDEMP2")
    key = "IDEMP-TEST-REPLAY-2"
    now = datetime.now(UTC).replace(tzinfo=None)
    base_kwargs = {
        "key": key,
        "correlation_id": "CALL-IDEMP-2",
        "claim_id": seeded["claim_id"],
        "source_call_id": "CALL-IDEMP-2",
        "preferred_contact_method": "PHONE",
        "now": now,
        "config": ComplaintsConfig(),
    }

    await complaints_service.create_complaint(
        db_session_committed,
        complaint_category="REPAIR_QUALITY",
        customer_statement_summary="The repair work is substandard",
        severity="HIGH",
        **base_kwargs,
    )

    try:
        await complaints_service.create_complaint(
            db_session_committed,
            complaint_category="CLAIM_DELAY",  # different category, same key
            customer_statement_summary="Completely different complaint",
            severity="LOW",
            **base_kwargs,
        )
        raised = False
    except IdempotencyKeyReuseError:
        raised = True

    assert raised
