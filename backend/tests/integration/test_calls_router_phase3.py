"""calls/router.py's Phase 3 additions — GET /{call_id}/transcript, /summary, /intents,
/sentiment. Zero Temporal dependency (rows are seeded directly), same shape as Phase 1's
claims/router.py tests — mirrors tests/integration/test_calls_router.py's `client` fixture.
"""

import httpx
import pytest

from src.calls import service as calls_service
from src.database import get_db
from src.main import app
from tests.unit.test_phase3_insert_only import _seed_call_attempt

pytestmark = pytest.mark.integration


@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


async def test_get_transcript_returns_seeded_turns_ordered(client, db_session):
    attempt = await _seed_call_attempt(db_session, suffix="ROUTER-CT")
    await calls_service.record_transcript_turn(
        db_session,
        call_attempt_id=attempt.id,
        turn_index=1,
        speaker="AI",
        redacted_text="How can I help?",
        language="en",
    )
    await calls_service.record_transcript_turn(
        db_session,
        call_attempt_id=attempt.id,
        turn_index=0,
        speaker="CUSTOMER",
        redacted_text="Hello",
        language="en",
    )
    await db_session.commit()

    response = await client.get(f"/calls/{attempt.id}/transcript")
    assert response.status_code == 200
    body = response.json()
    assert [t["turn_index"] for t in body] == [0, 1]
    assert [t["speaker"] for t in body] == ["CUSTOMER", "AI"]


async def test_get_transcript_404_for_unknown_call(client):
    response = await client.get("/calls/CALL-DOES-NOT-EXIST/transcript")
    assert response.status_code == 404


async def test_get_summary_returns_null_when_not_yet_generated(client, db_session):
    attempt = await _seed_call_attempt(db_session, suffix="ROUTER-CS-NULL")
    await db_session.commit()

    response = await client.get(f"/calls/{attempt.id}/summary")
    assert response.status_code == 200
    assert response.json() is None


async def test_get_summary_returns_row_when_present(client, db_session):
    attempt = await _seed_call_attempt(db_session, suffix="ROUTER-CS")
    await calls_service.record_call_summary(
        db_session, call_attempt_id=attempt.id, summary_text="All resolved."
    )
    await db_session.commit()

    response = await client.get(f"/calls/{attempt.id}/summary")
    assert response.status_code == 200
    assert response.json()["summary_text"] == "All resolved."


async def test_get_intents_returns_seeded_rows(client, db_session):
    attempt = await _seed_call_attempt(db_session, suffix="ROUTER-CI")
    await calls_service.record_customer_intent(
        db_session, call_attempt_id=attempt.id, intent="ASK_QUESTION", topic="ETA"
    )
    await db_session.commit()

    response = await client.get(f"/calls/{attempt.id}/intents")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["intent"] == "ASK_QUESTION"


async def test_get_sentiment_returns_seeded_rows(client, db_session):
    attempt = await _seed_call_attempt(db_session, suffix="ROUTER-SE")
    await calls_service.record_sentiment_event(
        db_session,
        call_attempt_id=attempt.id,
        turn_index=0,
        sentiment="NEGATIVE",
        signal="DELAY_DISSATISFACTION",
    )
    await db_session.commit()

    response = await client.get(f"/calls/{attempt.id}/sentiment")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["signal"] == "DELAY_DISSATISFACTION"
