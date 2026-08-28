"""The query-to-metric map — .claude/specs/phase-3-backend-spec.md §5.2, verbatim. Every
function takes `since`/`until` (required, no implicit default — see router.py) and reads
across domains directly; reporting/ owns no tables of its own.

Two deliberate departures from "just query CallAttempt.disposition_code" worth calling out
inline, not just here:
- "concurrent-call conflicts prevented" reads AuditEvent, not CallAttempt — campaigns/
  workflows.py::_finalize_concurrent_conflict never creates a CallAttempt row (the
  workflow that would create one never started).
- "silent-call technical failure rate," "rejected/unreachable/invalid-contact-number
  counts," and "fraud/SIU"/"vulnerable-customer" referral counts are real queries against
  real (currently always-empty) result sets — spec §0.10's documented honesty: nothing in
  this codebase produces those rows yet (Phase 5/6 territory), and a real query returning 0
  is not the "placeholder/mocked numbers" the phase's exit criteria forbids.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.actions.constants import ActionCode
from src.actions.models import Callback, ClaimAction, Escalation
from src.audit.models import AuditEvent, RuntimeFailureEvent
from src.calls.constants import DispositionCode
from src.calls.models import CallAttempt, CallLatencySample, SentimentEvent
from src.campaigns.models import CallJob
from src.complaints.models import Complaint
from src.reporting.schemas import (
    CustomerExperienceRead,
    EscalationAnalyticsRead,
    NoAnswerAnalyticsRead,
    NoAnswerByAttemptNumber,
    NoAnswerByDay,
    NoAnswerByHour,
    OperationsOverviewRead,
    OutcomeFunnelRead,
    OutcomeFunnelStage,
    StatusAnalyticsRow,
)

_DROPPED_CODES = (
    DispositionCode.CALL_DROPPED_PRE_AUTH.value,
    DispositionCode.CALL_DROPPED_POST_AUTH.value,
)
_OTP_LOCKOUT_CODES = (DispositionCode.OTP_LOCKED.value, DispositionCode.OTP_ATTEMPTS_EXCEEDED.value)
_REFERRAL_ACTION_CODES = (
    ActionCode.FRAUD_SIU_REVIEW_REQUEST.value,
    ActionCode.VULNERABLE_CUSTOMER_SUPPORT_REQUEST.value,
)
_DISSATISFACTION_SIGNALS = ("NEGATIVE_SENTIMENT", "DELAY_DISSATISFACTION", "SERVICE_FAILURE")


async def _count_attempts(session: AsyncSession, since: datetime, until: datetime) -> int:
    return (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(CallAttempt.attempted_at.between(since, until))
        )
    ) or 0


async def get_operations_overview(
    session: AsyncSession, *, since: datetime, until: datetime
) -> OperationsOverviewRead:
    total_attempts = await _count_attempts(session, since, until)
    in_range = CallAttempt.attempted_at.between(since, until)

    calls_scheduled = (
        await session.scalar(
            select(func.count(CallJob.id)).where(CallJob.created_at.between(since, until))
        )
    ) or 0

    customer_reached = (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(
                in_range, CallAttempt.customer_reached.is_(True)
            )
        )
    ) or 0
    right_party = (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(in_range, CallAttempt.right_party.is_(True))
        )
    ) or 0
    verified = (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(in_range, CallAttempt.verified.is_(True))
        )
    ) or 0
    statuses_delivered = (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(
                in_range, CallAttempt.status_delivered.is_not(None)
            )
        )
    ) or 0
    ai_contained = (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(
                in_range, CallAttempt.resolution == "FULLY_RESOLVED_BY_AI"
            )
        )
    ) or 0
    no_answer = (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(
                in_range, CallAttempt.disposition_code == DispositionCode.NO_ANSWER
            )
        )
    ) or 0
    dropped = (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(
                in_range, CallAttempt.disposition_code.in_(_DROPPED_CODES)
            )
        )
    ) or 0
    dtmf_fallback = (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(
                in_range, CallAttempt.disposition_code == DispositionCode.DTMF_FALLBACK_ACTIVATED
            )
        )
    ) or 0
    otp_lockouts = (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(
                in_range, CallAttempt.disposition_code.in_(_OTP_LOCKOUT_CODES)
            )
        )
    ) or 0
    silent_call_failures = (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(
                in_range,
                CallAttempt.disposition_code == DispositionCode.SILENT_CALL_TECHNICAL_FAILURE,
            )
        )
    ) or 0

    actions_created = (
        await session.scalar(
            select(func.count(ClaimAction.id)).where(ClaimAction.created_at.between(since, until))
        )
    ) or 0
    complaints_created = (
        await session.scalar(
            select(func.count(Complaint.id)).where(Complaint.created_at.between(since, until))
        )
    ) or 0
    escalations = (
        await session.scalar(
            select(func.count(Escalation.id)).where(Escalation.created_at.between(since, until))
        )
    ) or 0
    callbacks = (
        await session.scalar(
            select(func.count(Callback.id)).where(Callback.created_at.between(since, until))
        )
    ) or 0
    referrals = (
        await session.scalar(
            select(func.count(ClaimAction.id)).where(
                ClaimAction.created_at.between(since, until),
                ClaimAction.action_code.in_(_REFERRAL_ACTION_CODES),
            )
        )
    ) or 0
    fraud_referrals = (
        await session.scalar(
            select(func.count(ClaimAction.id)).where(
                ClaimAction.created_at.between(since, until),
                ClaimAction.action_code == ActionCode.FRAUD_SIU_REVIEW_REQUEST,
            )
        )
    ) or 0
    vulnerable_referrals = referrals - fraud_referrals

    avg_duration = await session.scalar(
        select(func.avg(CallAttempt.duration_seconds)).where(in_range)
    )

    # Concurrent-call conflicts: AuditEvent, never CallAttempt — see module docstring.
    concurrent_conflicts = (
        await session.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.created_at.between(since, until),
                AuditEvent.reason_code == "CONCURRENT_CALL_CONFLICT",
            )
        )
    ) or 0

    # Model/STT/TTS failure rate — RuntimeFailureEvent, extended by spec §5.3 to cover
    # these components (previously only "BACKEND", from deliver_status's
    # with_runtime_recovery). Backend dependency failure rate reads the same table.
    stt_llm_tts_failures = (
        await session.scalar(
            select(func.count(RuntimeFailureEvent.id)).where(
                RuntimeFailureEvent.created_at.between(since, until),
                RuntimeFailureEvent.component.in_(("STT", "LLM", "TTS")),
            )
        )
    ) or 0
    backend_failures = (
        await session.scalar(
            select(func.count(RuntimeFailureEvent.id)).where(
                RuntimeFailureEvent.created_at.between(since, until),
                RuntimeFailureEvent.component == "BACKEND",
            )
        )
    ) or 0

    p50, p95, p99 = await _latency_percentiles(session, since, until)

    def _rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    return OperationsOverviewRead(
        calls_scheduled=calls_scheduled,
        calls_attempted=total_attempts,
        human_answer_rate=_rate(customer_reached, total_attempts),
        right_party_contact_rate=_rate(right_party, customer_reached),
        verification_success_rate=_rate(verified, right_party),
        statuses_delivered=statuses_delivered,
        ai_contained_calls=ai_contained,
        actions_created=actions_created,
        complaints_created=complaints_created,
        human_escalations=escalations,
        callbacks_scheduled=callbacks,
        no_answer_rate=_rate(no_answer, total_attempts),
        avg_call_duration_seconds=float(avg_duration) if avg_duration is not None else None,
        latency_p50_ms=p50,
        latency_p95_ms=p95,
        latency_p99_ms=p99,
        silent_call_technical_failure_rate=_rate(silent_call_failures, total_attempts),
        backend_dependency_failure_rate=_rate(backend_failures, total_attempts),
        model_stt_tts_failure_rate=_rate(stt_llm_tts_failures, total_attempts),
        dtmf_fallback_rate=_rate(dtmf_fallback, total_attempts),
        concurrent_call_conflicts_prevented=concurrent_conflicts,
        dropped_call_rate=_rate(dropped, total_attempts),
        otp_lockouts=otp_lockouts,
        fraud_siu_referrals=fraud_referrals,
        vulnerable_customer_referrals=vulnerable_referrals,
    )


async def _latency_percentiles(
    session: AsyncSession, since: datetime, until: datetime
) -> tuple[float | None, float | None, float | None]:
    stmt = select(
        func.percentile_cont(0.5).within_group(CallLatencySample.latency_ms),
        func.percentile_cont(0.95).within_group(CallLatencySample.latency_ms),
        func.percentile_cont(0.99).within_group(CallLatencySample.latency_ms),
    ).where(CallLatencySample.created_at.between(since, until))
    row = (await session.execute(stmt)).one()
    return (
        float(row[0]) if row[0] is not None else None,
        float(row[1]) if row[1] is not None else None,
        float(row[2]) if row[2] is not None else None,
    )


async def get_outcome_funnel(
    session: AsyncSession, *, since: datetime, until: datetime
) -> OutcomeFunnelRead:
    in_range = CallAttempt.attempted_at.between(since, until)

    scheduled = (
        await session.scalar(
            select(func.count(CallJob.id)).where(CallJob.created_at.between(since, until))
        )
    ) or 0
    attempted = await _count_attempts(session, since, until)
    answered = (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(
                in_range, CallAttempt.customer_reached.is_(True)
            )
        )
    ) or 0
    right_party = (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(in_range, CallAttempt.right_party.is_(True))
        )
    ) or 0
    authenticated = (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(in_range, CallAttempt.verified.is_(True))
        )
    ) or 0
    status_delivered = (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(
                in_range, CallAttempt.status_delivered.is_not(None)
            )
        )
    ) or 0
    resolved_by_ai = (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(
                in_range, CallAttempt.resolution == "FULLY_RESOLVED_BY_AI"
            )
        )
    ) or 0

    counts = [
        scheduled,
        attempted,
        answered,
        right_party,
        authenticated,
        status_delivered,
        resolved_by_ai,
    ]
    names = [
        "Scheduled",
        "Attempted",
        "Answered",
        "Right Party",
        "Authenticated",
        "Status Delivered",
        "Resolved by AI",
    ]
    stages = []
    previous = None
    for name, count in zip(names, counts, strict=True):
        conversion: float | None = round(count / previous, 4) if previous else None
        stages.append(
            OutcomeFunnelStage(stage=name, count=count, conversion_from_previous=conversion)
        )
        previous = count
    return OutcomeFunnelRead(stages=stages)


async def get_no_answer_analytics(
    session: AsyncSession, *, since: datetime, until: datetime
) -> NoAnswerAnalyticsRead:
    in_range = CallAttempt.attempted_at.between(since, until)

    hour_col = func.extract("hour", CallAttempt.attempted_at)
    hour_rows = (
        await session.execute(
            select(
                hour_col,
                func.count(CallAttempt.id).filter(
                    CallAttempt.disposition_code == DispositionCode.NO_ANSWER
                ),
                func.count(CallAttempt.id),
            )
            .where(in_range)
            .group_by(hour_col)
            .order_by(hour_col)
        )
    ).all()
    by_hour = [
        NoAnswerByHour(hour=int(h), no_answer_count=na, total_count=total)
        for h, na, total in hour_rows
    ]

    day_col = func.date_trunc("day", CallAttempt.attempted_at)
    day_rows = (
        await session.execute(
            select(
                day_col,
                func.count(CallAttempt.id).filter(
                    CallAttempt.disposition_code == DispositionCode.NO_ANSWER
                ),
                func.count(CallAttempt.id),
            )
            .where(in_range)
            .group_by(day_col)
            .order_by(day_col)
        )
    ).all()
    by_day = [
        NoAnswerByDay(day=d.date().isoformat(), no_answer_count=na, total_count=total)
        for d, na, total in day_rows
    ]

    attempt_rows = (
        await session.execute(
            select(
                CallAttempt.attempt_number,
                func.count(CallAttempt.id).filter(CallAttempt.customer_reached.is_(True)),
                func.count(CallAttempt.id),
            )
            .where(in_range)
            .group_by(CallAttempt.attempt_number)
            .order_by(CallAttempt.attempt_number)
        )
    ).all()
    by_attempt_number = [
        NoAnswerByAttemptNumber(
            attempt_number=n,
            answer_rate=round(reached / total, 4) if total else 0.0,
            total_count=total,
        )
        for n, reached, total in attempt_rows
    ]

    rejected = (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(
                in_range, CallAttempt.disposition_code == DispositionCode.CALL_REJECTED
            )
        )
    ) or 0
    voicemail = (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(
                in_range, CallAttempt.voicemail_detected.is_(True)
            )
        )
    ) or 0
    unreachable = (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(
                in_range,
                CallAttempt.disposition_code.in_(
                    (DispositionCode.NUMBER_UNREACHABLE, DispositionCode.INVALID_CONTACT_NUMBER)
                ),
            )
        )
    ) or 0
    successful_callbacks = (
        await session.scalar(
            select(func.count(Callback.id)).where(
                Callback.created_at.between(since, until), Callback.status == "COMPLETED"
            )
        )
    ) or 0

    return NoAnswerAnalyticsRead(
        by_hour=by_hour,
        by_day=by_day,
        by_attempt_number=by_attempt_number,
        rejected_count=rejected,
        voicemail_count=voicemail,
        unreachable_count=unreachable,
        successful_callbacks=successful_callbacks,
    )


async def get_status_analytics(
    session: AsyncSession, *, since: datetime, until: datetime
) -> list[StatusAnalyticsRow]:
    in_range = CallAttempt.attempted_at.between(since, until)
    rows = (
        await session.execute(
            select(
                CallAttempt.status_delivered,
                func.count(CallAttempt.id),
                func.count(CallAttempt.id).filter(
                    CallAttempt.disposition_code
                    == DispositionCode.SUCCESS_STATUS_AND_QUERY_RESOLVED
                ),
                func.count(CallAttempt.id).filter(
                    CallAttempt.disposition_code == DispositionCode.SUCCESS_HUMAN_TRANSFER
                ),
            )
            .where(in_range, CallAttempt.status_delivered.is_not(None))
            .group_by(CallAttempt.status_delivered)
            .order_by(CallAttempt.status_delivered)
        )
    ).all()
    return [
        StatusAnalyticsRow(
            status=status,
            total_calls=total,
            question_rate=round(questions / total, 4) if total else 0.0,
            escalation_rate=round(escalations / total, 4) if total else 0.0,
        )
        for status, total, questions, escalations in rows
    ]


async def get_customer_experience(
    session: AsyncSession, *, since: datetime, until: datetime
) -> CustomerExperienceRead:
    in_range = CallAttempt.attempted_at.between(since, until)

    # "Initial sentiment" = each call's MIN(turn_index) per-turn row; "final sentiment" =
    # the call-level (turn_index IS NULL, signal IS NULL) row generate_call_summary writes
    # — spec §5.2's query design, .claude/specs/phase-3-backend-spec.md.
    initial_subq = (
        select(
            SentimentEvent.call_attempt_id,
            func.min(SentimentEvent.turn_index).label("min_turn"),
        )
        .where(SentimentEvent.turn_index.is_not(None))
        .group_by(SentimentEvent.call_attempt_id)
        .subquery()
    )
    initial_rows = (
        await session.execute(
            select(SentimentEvent.sentiment, func.count())
            .join(
                initial_subq,
                (SentimentEvent.call_attempt_id == initial_subq.c.call_attempt_id)
                & (SentimentEvent.turn_index == initial_subq.c.min_turn),
            )
            .join(CallAttempt, CallAttempt.id == SentimentEvent.call_attempt_id)
            .where(in_range)
            .group_by(SentimentEvent.sentiment)
        )
    ).all()
    initial_breakdown = {s or "UNKNOWN": c for s, c in initial_rows}

    final_rows = (
        await session.execute(
            select(SentimentEvent.sentiment, func.count())
            .join(CallAttempt, CallAttempt.id == SentimentEvent.call_attempt_id)
            .where(
                in_range,
                SentimentEvent.turn_index.is_(None),
                SentimentEvent.signal.is_(None),
                SentimentEvent.sentiment.is_not(None),
            )
            .group_by(SentimentEvent.sentiment)
        )
    ).all()
    final_breakdown = {s or "UNKNOWN": c for s, c in final_rows}

    total_attempts = await _count_attempts(session, since, until)
    dissatisfied_calls = (
        await session.scalar(
            select(func.count(func.distinct(SentimentEvent.call_attempt_id)))
            .join(CallAttempt, CallAttempt.id == SentimentEvent.call_attempt_id)
            .where(in_range, SentimentEvent.signal.in_(_DISSATISFACTION_SIGNALS))
        )
    ) or 0
    complaints_created = (
        await session.scalar(
            select(func.count(Complaint.id)).where(Complaint.created_at.between(since, until))
        )
    ) or 0
    repeated_contact_customers = (
        await session.scalar(
            select(func.count(func.distinct(CallAttempt.customer_id)))
            .join(SentimentEvent, SentimentEvent.call_attempt_id == CallAttempt.id)
            .where(in_range, SentimentEvent.signal == "REPEATED_CONTACT")
        )
    ) or 0
    calls_requiring_humans = (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(
                in_range, CallAttempt.disposition_code == DispositionCode.SUCCESS_HUMAN_TRANSFER
            )
        )
    ) or 0

    return CustomerExperienceRead(
        initial_sentiment_breakdown=initial_breakdown,
        final_sentiment_breakdown=final_breakdown,
        dissatisfaction_rate=round(dissatisfied_calls / total_attempts, 4)
        if total_attempts
        else 0.0,
        complaint_rate=round(complaints_created / total_attempts, 4) if total_attempts else 0.0,
        repeated_contact_customers=repeated_contact_customers,
        calls_requiring_humans=calls_requiring_humans,
    )


async def get_escalation_analytics(
    session: AsyncSession, *, since: datetime, until: datetime
) -> EscalationAnalyticsRead:
    in_range = Escalation.created_at.between(since, until)

    total = (await session.scalar(select(func.count(Escalation.id)).where(in_range))) or 0

    status_rows = (
        await session.execute(
            select(Escalation.status, func.count()).where(in_range).group_by(Escalation.status)
        )
    ).all()
    by_status: dict[str, int] = dict(status_rows)  # type: ignore[arg-type]

    reason_rows = (
        await session.execute(
            select(Escalation.reason, func.count()).where(in_range).group_by(Escalation.reason)
        )
    ).all()
    by_reason: dict[str, int] = dict(reason_rows)  # type: ignore[arg-type]

    warm_transfers = (
        await session.scalar(
            select(func.count(CallAttempt.id)).where(
                CallAttempt.attempted_at.between(since, until),
                CallAttempt.disposition_code == DispositionCode.SUCCESS_HUMAN_TRANSFER,
            )
        )
    ) or 0

    return EscalationAnalyticsRead(
        total_escalations=total,
        by_status=by_status,
        by_reason=by_reason,
        warm_transfer_count=warm_transfers,
    )
