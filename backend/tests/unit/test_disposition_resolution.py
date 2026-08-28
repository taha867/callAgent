"""Table-driven tests for src.calls.disposition.resolve_disposition — written before any
workflow code consumes it (.claude/specs/phase-1-backend-implementation-plan.md Batch 5),
since every later exit-criteria branch's assertion depends on this truth table being right
in isolation first.
"""

import pytest

from src.calls.constants import CallState, DispositionCode
from src.calls.disposition import (
    DispositionContext,
    UnresolvedDispositionError,
    resolve_disposition,
)

# (context kwargs, expected DispositionCode) — one row per branch this phase's exit
# criteria (phases/phase-1-deterministic-core.md) requires, per
# .claude/specs/phase-1-backend-spec.md §16's traceability table.
_CASES: list[tuple[dict, DispositionCode]] = [
    ({"final_state": CallState.NO_ANSWER}, DispositionCode.NO_ANSWER),
    ({"final_state": CallState.VOICEMAIL}, DispositionCode.VOICEMAIL),
    ({"final_state": CallState.FAILED}, DispositionCode.NETWORK_FAILURE),
    ({"final_state": CallState.WRONG_PARTY}, DispositionCode.WRONG_PARTY),
    ({"final_state": CallState.CUSTOMER_UNAVAILABLE}, DispositionCode.RIGHT_PARTY_NOT_AVAILABLE),
    ({"final_state": CallState.AUTH_FAILED}, DispositionCode.AUTH_FAILED),
    (
        {"final_state": CallState.CLOSE, "status_delivered": True},
        DispositionCode.SUCCESS_STATUS_DELIVERED,
    ),
    (
        {
            "final_state": CallState.CLOSE,
            "status_delivered": True,
            "question_resolved": True,
        },
        DispositionCode.SUCCESS_STATUS_AND_QUERY_RESOLVED,
    ),
    (
        {"final_state": CallState.CLOSE, "complaint_created": True},
        DispositionCode.SUCCESS_COMPLAINT_REGISTERED,
    ),
    (
        {"final_state": CallState.CLOSE, "action_created": True},
        DispositionCode.SUCCESS_ACTION_CREATED,
    ),
    (
        {"final_state": CallState.CLOSE, "human_transferred": True},
        DispositionCode.SUCCESS_HUMAN_TRANSFER,
    ),
    ({"final_state": CallState.DIALING, "otp_locked": True}, DispositionCode.OTP_LOCKED),
    (
        {"final_state": CallState.DIALING, "otp_attempts_exceeded": True},
        DispositionCode.OTP_ATTEMPTS_EXCEEDED,
    ),
    (
        {"final_state": CallState.DIALING, "call_dropped": True, "was_authenticated": False},
        DispositionCode.CALL_DROPPED_PRE_AUTH,
    ),
    (
        {"final_state": CallState.DIALING, "call_dropped": True, "was_authenticated": True},
        DispositionCode.CALL_DROPPED_POST_AUTH,
    ),
    (
        {"final_state": CallState.DIALING, "callback_requested": True},
        DispositionCode.CALLBACK_REQUESTED,
    ),
    (
        {"final_state": CallState.DIALING, "backend_unavailable": True},
        DispositionCode.BACKEND_SYSTEM_FAILURE,
    ),
]


@pytest.mark.parametrize(("kwargs", "expected"), _CASES)
def test_resolve_disposition(kwargs, expected):
    assert resolve_disposition(DispositionContext(**kwargs)) == expected


def test_close_with_no_flags_raises():
    """A CallState.CLOSE with nothing else true is a workflow bug, not a valid outcome —
    resolve_disposition must refuse to guess."""
    with pytest.raises(UnresolvedDispositionError):
        resolve_disposition(DispositionContext(final_state=CallState.CLOSE))


def test_non_terminal_state_with_no_flags_raises():
    """A CallState the workflow is still mid-transition through (e.g. DIALING) must never
    reach resolve_disposition without one of the flag-based outcomes explaining why —
    catches a future CallState added without updating this resolver."""
    with pytest.raises(UnresolvedDispositionError):
        resolve_disposition(DispositionContext(final_state=CallState.RIGHT_PARTY_CHECK))


def test_close_precedence_status_and_query_beats_status_alone():
    """Both status_delivered and question_resolved true must produce the more specific
    combined code, not the plain status-delivered one."""
    ctx = DispositionContext(
        final_state=CallState.CLOSE, status_delivered=True, question_resolved=True
    )
    assert resolve_disposition(ctx) == DispositionCode.SUCCESS_STATUS_AND_QUERY_RESOLVED


def test_otp_locked_takes_precedence_over_otp_attempts_exceeded():
    ctx = DispositionContext(
        final_state=CallState.DIALING, otp_locked=True, otp_attempts_exceeded=True
    )
    assert resolve_disposition(ctx) == DispositionCode.OTP_LOCKED


def test_complaint_created_takes_precedence_over_plain_status_delivered():
    """Status is always delivered before the follow-up stage that creates a complaint
    (spec §14/§18) — status_delivered=True co-occurs with complaint_created=True on every
    such call, and the more specific outcome must win."""
    ctx = DispositionContext(
        final_state=CallState.CLOSE, status_delivered=True, complaint_created=True
    )
    assert resolve_disposition(ctx) == DispositionCode.SUCCESS_COMPLAINT_REGISTERED


def test_action_created_takes_precedence_over_plain_status_delivered():
    ctx = DispositionContext(
        final_state=CallState.CLOSE, status_delivered=True, action_created=True
    )
    assert resolve_disposition(ctx) == DispositionCode.SUCCESS_ACTION_CREATED


def test_backend_unavailable_beats_a_fallback_action_created_alongside_it():
    """spec §14 Type E: a best-effort BACKEND_DATA_VERIFICATION_REQUEST action may be
    created as part of backend-failure recovery — that must never make the disposition
    look like an ordinary successful action-created call."""
    ctx = DispositionContext(
        final_state=CallState.CLOSE,
        status_delivered=False,
        action_created=True,
        backend_unavailable=True,
    )
    assert resolve_disposition(ctx) == DispositionCode.BACKEND_SYSTEM_FAILURE


def test_call_dropped_beats_status_delivered_and_action_created():
    ctx = DispositionContext(
        final_state=CallState.CLOSE,
        status_delivered=True,
        action_created=True,
        call_dropped=True,
        was_authenticated=True,
    )
    assert resolve_disposition(ctx) == DispositionCode.CALL_DROPPED_POST_AUTH


def test_human_transferred_takes_precedence_over_everything_else():
    ctx = DispositionContext(
        final_state=CallState.CLOSE,
        status_delivered=True,
        complaint_created=True,
        action_created=True,
        human_transferred=True,
    )
    assert resolve_disposition(ctx) == DispositionCode.SUCCESS_HUMAN_TRANSFER
