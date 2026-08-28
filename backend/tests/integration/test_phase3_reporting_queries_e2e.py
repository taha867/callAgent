"""reporting/router.py's 6 endpoints — seeds CallAttempt/SentimentEvent/CallLatencySample/
AuditEvent/RuntimeFailureEvent/ClaimAction/Complaint/Escalation/Callback/CallJob rows
directly, hits every endpoint, and asserts against hand-computed expected numbers. This is
what proves .claude/specs/phase-3-backend-spec.md §5.2's query map is correct, not just
plausible-looking SQL.
"""

from datetime import datetime, timedelta

import httpx
import pytest

from src.actions.constants import ActionCode
from src.actions.models import Callback, ClaimAction, Escalation
from src.audit.models import AuditEvent, RuntimeFailureEvent
from src.calls.constants import DispositionCode
from src.calls.models import CallAttempt, CallLatencySample, SentimentEvent
from src.campaigns.models import CallJob, OutboundCampaign
from src.claims.constants import ClaimStage
from src.claims.models import MotorClaim, MotorPolicy
from src.complaints.models import Complaint
from src.customers.models import Customer
from src.database import get_db
from src.main import app

pytestmark = pytest.mark.integration

_SINCE = datetime(2026, 1, 1)
_UNTIL = datetime(2026, 1, 2)
_MID = datetime(2026, 1, 1, 12, 0, 0)


@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


async def _seed(db) -> dict:
    db.add(Customer(id="CUST-RPT-1", full_name="x", phone_e164="+1"))
    db.add(Customer(id="CUST-RPT-2", full_name="y", phone_e164="+2"))
    await db.flush()
    db.add(
        MotorPolicy(
            id="POL-RPT-1",
            customer_id="CUST-RPT-1",
            policy_number="P1",
            vehicle_plate="X",
            vehicle_make_model="Y",
        )
    )
    db.add(
        MotorPolicy(
            id="POL-RPT-2",
            customer_id="CUST-RPT-2",
            policy_number="P2",
            vehicle_plate="X",
            vehicle_make_model="Y",
        )
    )
    await db.flush()
    db.add(
        MotorClaim(
            id="CLM-RPT-1",
            policy_id="POL-RPT-1",
            customer_id="CUST-RPT-1",
            claim_stage=ClaimStage.REPAIR_AUTHORIZED,
            language="en",
        )
    )
    db.add(
        MotorClaim(
            id="CLM-RPT-2",
            policy_id="POL-RPT-2",
            customer_id="CUST-RPT-2",
            claim_stage=ClaimStage.REPAIR_AUTHORIZED,
            language="en",
        )
    )
    await db.flush()

    db.add(OutboundCampaign(id="CAMP-RPT-1", name="x", reason="STATUS_UPDATE"))
    await db.flush()
    db.add(
        CallJob(
            id="JOB-RPT-1",
            campaign_id="CAMP-RPT-1",
            customer_id="CUST-RPT-1",
            claim_id="CLM-RPT-1",
            status="DONE",
            created_at=_MID,
        )
    )
    db.add(
        CallJob(
            id="JOB-RPT-2",
            campaign_id="CAMP-RPT-1",
            customer_id="CUST-RPT-2",
            claim_id="CLM-RPT-2",
            status="DONE",
            created_at=_MID,
        )
    )
    db.add(
        CallJob(
            id="JOB-RPT-OUT-OF-RANGE",
            campaign_id="CAMP-RPT-1",
            customer_id="CUST-RPT-2",
            claim_id="CLM-RPT-2",
            status="DONE",
            created_at=_UNTIL + timedelta(days=1),
        )
    )

    # Attempt 1: fully successful, status delivered + question resolved
    db.add(
        CallAttempt(
            id="CALL-RPT-1",
            customer_id="CUST-RPT-1",
            claim_id="CLM-RPT-1",
            attempt_number=1,
            attempted_at=_MID,
            customer_reached=True,
            right_party=True,
            verified=True,
            verification_level="L1",
            status_delivered="MOTOR_REPAIR_AUTHORIZED",
            resolution="FULLY_RESOLVED_BY_AI",
            disposition_code=DispositionCode.SUCCESS_STATUS_AND_QUERY_RESOLVED,
            duration_seconds=120,
        )
    )
    # Attempt 2: no answer
    db.add(
        CallAttempt(
            id="CALL-RPT-2",
            customer_id="CUST-RPT-2",
            claim_id="CLM-RPT-2",
            attempt_number=1,
            attempted_at=_MID,
            customer_reached=False,
            disposition_code=DispositionCode.NO_ANSWER,
        )
    )
    # Attempt 3: human transfer (escalation), same status as attempt 1
    db.add(
        CallAttempt(
            id="CALL-RPT-3",
            customer_id="CUST-RPT-2",
            claim_id="CLM-RPT-2",
            attempt_number=2,
            attempted_at=_MID,
            customer_reached=True,
            right_party=True,
            verified=True,
            verification_level="L1",
            status_delivered="MOTOR_REPAIR_AUTHORIZED",
            resolution="HUMAN_TRANSFER",
            disposition_code=DispositionCode.SUCCESS_HUMAN_TRANSFER,
            duration_seconds=200,
        )
    )
    await db.flush()

    db.add(
        ClaimAction(
            id="ACT-RPT-1",
            claim_id="CLM-RPT-1",
            action_code=ActionCode.CLAIMS_TEAM_QUERY,
            summary="x",
            created_at=_MID,
        )
    )
    db.add(
        Complaint(
            id="COMP-RPT-1",
            claim_id="CLM-RPT-1",
            source_call_id="CALL-RPT-1",
            complaint_category="CLAIM_DELAY",
            customer_statement_summary="x",
            severity="MEDIUM",
            preferred_contact_method="PHONE",
            acknowledgment_due_at=_MID + timedelta(hours=24),
            resolution_due_at=_MID + timedelta(days=9),
            sla_source="TEST",
            created_at=_MID,
        )
    )
    db.add(
        Escalation(
            id="ESC-RPT-1",
            call_id="CALL-RPT-3",
            reason="CUSTOMER_REQUESTED_HUMAN",
            context_snapshot={},
            status="OPEN",
            created_at=_MID,
        )
    )
    db.add(
        Callback(
            id="CB-RPT-1",
            customer_id="CUST-RPT-1",
            callback_window_start=_MID,
            callback_window_end=_MID + timedelta(hours=2),
            reason="TEST",
            status="COMPLETED",
            created_at=_MID,
        )
    )

    db.add(
        AuditEvent(
            call_id="CALL-RPT-CONFLICT",
            reason_code="CONCURRENT_CALL_CONFLICT",
            decision="CONCURRENT_CALL_CONFLICT",
            created_at=_MID,
        )
    )
    db.add(
        RuntimeFailureEvent(
            call_id="CALL-RPT-1",
            component="STT",
            failure_type="TimeoutError",
            recovery_action="SAFE_TERMINATION",
            created_at=_MID,
        )
    )

    # Sentiment: attempt 1 initial NEUTRAL (turn 0), final POSITIVE (call-level)
    db.add(
        SentimentEvent(
            call_attempt_id="CALL-RPT-1", turn_index=0, sentiment="NEUTRAL", created_at=_MID
        )
    )
    db.add(
        SentimentEvent(
            call_attempt_id="CALL-RPT-1", turn_index=1, sentiment="POSITIVE", created_at=_MID
        )
    )
    db.add(
        SentimentEvent(
            call_attempt_id="CALL-RPT-1",
            turn_index=None,
            sentiment="POSITIVE",
            signal=None,
            created_at=_MID,
        )
    )
    # attempt 3: dissatisfaction signal
    db.add(
        SentimentEvent(
            call_attempt_id="CALL-RPT-3",
            turn_index=0,
            sentiment="NEGATIVE",
            signal="DELAY_DISSATISFACTION",
            created_at=_MID,
        )
    )

    db.add(
        CallLatencySample(
            call_attempt_id="CALL-RPT-1", turn_index=0, latency_ms=800, created_at=_MID
        )
    )
    db.add(
        CallLatencySample(
            call_attempt_id="CALL-RPT-1", turn_index=1, latency_ms=1200, created_at=_MID
        )
    )

    await db.commit()
    return {}


async def test_operations_overview(client, db_session):
    await _seed(db_session)
    response = await client.get(
        "/reporting/operations-overview",
        params={"since": _SINCE.isoformat(), "until": _UNTIL.isoformat()},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["calls_scheduled"] == 2  # JOB-RPT-1/2, not the out-of-range one
    assert body["calls_attempted"] == 3
    assert body["human_answer_rate"] == round(2 / 3, 4)  # 2 of 3 reached
    assert body["statuses_delivered"] == 2
    assert body["ai_contained_calls"] == 1
    assert body["actions_created"] == 1
    assert body["complaints_created"] == 1
    assert body["human_escalations"] == 1
    assert body["callbacks_scheduled"] == 1
    assert body["no_answer_rate"] == round(1 / 3, 4)
    assert body["avg_call_duration_seconds"] == pytest.approx((120 + 200) / 2)
    assert body["concurrent_call_conflicts_prevented"] == 1
    assert body["model_stt_tts_failure_rate"] == round(1 / 3, 4)
    assert body["fraud_siu_referrals"] == 0
    assert body["vulnerable_customer_referrals"] == 0
    assert body["latency_p50_ms"] is not None


async def test_outcome_funnel(client, db_session):
    await _seed(db_session)
    response = await client.get(
        "/reporting/outcome-funnel",
        params={"since": _SINCE.isoformat(), "until": _UNTIL.isoformat()},
    )
    assert response.status_code == 200, response.text
    stages = {s["stage"]: s["count"] for s in response.json()["stages"]}
    assert stages["Scheduled"] == 2
    assert stages["Attempted"] == 3
    assert stages["Answered"] == 2
    assert stages["Resolved by AI"] == 1


async def test_no_answer_analytics(client, db_session):
    await _seed(db_session)
    response = await client.get(
        "/reporting/no-answer-analytics",
        params={"since": _SINCE.isoformat(), "until": _UNTIL.isoformat()},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert sum(row["no_answer_count"] for row in body["by_hour"]) == 1
    assert body["successful_callbacks"] == 1
    by_attempt = {row["attempt_number"]: row for row in body["by_attempt_number"]}
    assert by_attempt[1]["total_count"] == 2  # CALL-RPT-1 and CALL-RPT-2 are both attempt_number=1
    assert by_attempt[2]["total_count"] == 1


async def test_status_analytics(client, db_session):
    await _seed(db_session)
    response = await client.get(
        "/reporting/status-analytics",
        params={"since": _SINCE.isoformat(), "until": _UNTIL.isoformat()},
    )
    assert response.status_code == 200, response.text
    rows = {r["status"]: r for r in response.json()}
    row = rows["MOTOR_REPAIR_AUTHORIZED"]
    assert row["total_calls"] == 2  # CALL-RPT-1 and CALL-RPT-3
    assert row["question_rate"] == round(1 / 2, 4)  # only CALL-RPT-1
    assert row["escalation_rate"] == round(1 / 2, 4)  # only CALL-RPT-3


async def test_customer_experience(client, db_session):
    await _seed(db_session)
    response = await client.get(
        "/reporting/customer-experience",
        params={"since": _SINCE.isoformat(), "until": _UNTIL.isoformat()},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["initial_sentiment_breakdown"].get("NEUTRAL") == 1  # CALL-RPT-1's turn 0
    assert body["initial_sentiment_breakdown"].get("NEGATIVE") == 1  # CALL-RPT-3's turn 0
    assert body["final_sentiment_breakdown"].get("POSITIVE") == 1  # CALL-RPT-1's call-level row
    assert body["dissatisfaction_rate"] == round(1 / 3, 4)  # CALL-RPT-3 only
    assert body["calls_requiring_humans"] == 1


async def test_escalation_analytics(client, db_session):
    await _seed(db_session)
    response = await client.get(
        "/reporting/escalation-analytics",
        params={"since": _SINCE.isoformat(), "until": _UNTIL.isoformat()},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_escalations"] == 1
    assert body["by_status"] == {"OPEN": 1}
    assert body["by_reason"] == {"CUSTOMER_REQUESTED_HUMAN": 1}
    assert body["warm_transfer_count"] == 1


async def test_missing_since_until_returns_422(client):
    response = await client.get("/reporting/operations-overview")
    assert response.status_code == 422


async def test_timezone_aware_since_until_does_not_500(client, db_session):
    """Regression — every real frontend caller sends a Z-suffixed (timezone-aware)
    .toISOString() value (.claude/specs/phase-3-frontend-spec.md §0.3), which FastAPI/
    Pydantic parses into a timezone-AWARE datetime. Every DateTime column in this codebase
    is naive TIMESTAMP WITHOUT TIME ZONE — binding a tz-aware datetime against one used to
    raise asyncpg.DataError ("can't subtract offset-naive and offset-aware datetimes"),
    a 500 caught live via a real browser check against this exact endpoint. get_range()
    (reporting/router.py) now strips tzinfo before any query runs."""
    await _seed(db_session)
    response = await client.get(
        "/reporting/operations-overview",
        params={"since": "2026-01-01T00:00:00.000Z", "until": "2026-01-02T00:00:00.000Z"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["complaints_created"] == 1
