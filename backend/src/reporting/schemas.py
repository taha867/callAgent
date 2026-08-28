"""reporting/'s response schemas — reporting/ owns no tables (.claude/specs/
phase-3-backend-spec.md §5), so there are no matching Create/Update schemas, only Read
shapes built from cross-domain aggregate queries.
"""

from pydantic import BaseModel


class OperationsOverviewRead(BaseModel):
    calls_scheduled: int
    calls_attempted: int
    human_answer_rate: float
    right_party_contact_rate: float
    verification_success_rate: float
    statuses_delivered: int
    ai_contained_calls: int
    actions_created: int
    complaints_created: int
    human_escalations: int
    callbacks_scheduled: int
    no_answer_rate: float
    avg_call_duration_seconds: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    latency_p99_ms: float | None
    silent_call_technical_failure_rate: float
    backend_dependency_failure_rate: float
    model_stt_tts_failure_rate: float
    dtmf_fallback_rate: float
    concurrent_call_conflicts_prevented: int
    dropped_call_rate: float
    otp_lockouts: int
    fraud_siu_referrals: int
    vulnerable_customer_referrals: int


class OutcomeFunnelStage(BaseModel):
    stage: str
    count: int
    conversion_from_previous: float | None  # None for the first stage


class OutcomeFunnelRead(BaseModel):
    stages: list[OutcomeFunnelStage]


class NoAnswerByHour(BaseModel):
    hour: int  # 0-23
    no_answer_count: int
    total_count: int


class NoAnswerByDay(BaseModel):
    day: str  # ISO date
    no_answer_count: int
    total_count: int


class NoAnswerByAttemptNumber(BaseModel):
    attempt_number: int
    answer_rate: float
    total_count: int


class NoAnswerAnalyticsRead(BaseModel):
    by_hour: list[NoAnswerByHour]
    by_day: list[NoAnswerByDay]
    by_attempt_number: list[NoAnswerByAttemptNumber]
    rejected_count: int
    voicemail_count: int
    unreachable_count: int
    successful_callbacks: int


class StatusAnalyticsRow(BaseModel):
    status: str  # CallAttempt.status_delivered's message key
    total_calls: int
    question_rate: float
    escalation_rate: float


class CustomerExperienceRead(BaseModel):
    initial_sentiment_breakdown: dict[str, int]
    final_sentiment_breakdown: dict[str, int]
    dissatisfaction_rate: float
    complaint_rate: float
    repeated_contact_customers: int
    calls_requiring_humans: int


class EscalationAnalyticsRead(BaseModel):
    total_escalations: int
    by_status: dict[str, int]
    by_reason: dict[str, int]
    warm_transfer_count: int
