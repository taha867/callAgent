"""CallState is data, not yet behavior — the actual state-machine transition logic lives in
CallSessionWorkflow (src/calls/workflows.py, Batch 11) and is exercised by
tests/integration/test_phase1_e2e.py's real Temporal workflow runs, not here. This file
covers what IS testable in isolation at this stage (.claude/specs/phase-1-backend-implementation-plan.md
Batch 5): that the CallState enum itself matches spec §3's diagram completely, and that
every terminal state resolve_disposition needs to resolve is actually present.
"""

from src.calls.constants import (
    FUTURE_GLOBAL_INTERRUPTS,
    MAX_CALL_SESSION_SECONDS,
    CallState,
    DispositionCode,
)
from src.calls.disposition import DispositionContext, resolve_disposition

# Every state named in spec §3's mermaid diagram (Master Call State Machine), verbatim.
_SPEC_STATES = {
    "CALL_QUEUED",
    "DIALING",
    "NO_ANSWER",
    "VOICEMAIL",
    "HUMAN_ANSWERED",
    "FAILED",
    "INTRODUCTION",
    "RIGHT_PARTY_CHECK",
    "WRONG_PARTY",
    "CUSTOMER_UNAVAILABLE",
    "AUTHENTICATION",
    "AUTH_RETRY",
    "AUTHENTICATED",
    "AUTH_FAILED",
    "PURPOSE_DISCLOSURE",
    "STATUS_DELIVERY",
    "FOLLOW_UP",
    "ACTION_REQUIRED",
    "COMPLAINT",
    "HUMAN_ESCALATION",
    "CALLBACK_REQUESTED",
    "CALLBACK_SCHEDULE",
    "RESOLVED",
    "RESOLUTION_SUMMARY",
    "TRANSFER_OR_CALLBACK",
    "CLOSE",
}

# The subset of terminal-ish CallState values resolve_disposition maps 1:1 without needing
# any DispositionContext flag beyond final_state itself.
_DIRECTLY_RESOLVED_STATES = {
    CallState.NO_ANSWER: DispositionCode.NO_ANSWER,
    CallState.VOICEMAIL: DispositionCode.VOICEMAIL,
    CallState.FAILED: DispositionCode.NETWORK_FAILURE,
    CallState.WRONG_PARTY: DispositionCode.WRONG_PARTY,
    CallState.CUSTOMER_UNAVAILABLE: DispositionCode.RIGHT_PARTY_NOT_AVAILABLE,
    CallState.AUTH_FAILED: DispositionCode.AUTH_FAILED,
}


def test_call_state_matches_spec_diagram_exactly():
    assert {m.value for m in CallState} == _SPEC_STATES


def test_call_state_count():
    assert len(CallState) == len(_SPEC_STATES) == 26


def test_directly_resolved_states_actually_resolve():
    for state, expected in _DIRECTLY_RESOLVED_STATES.items():
        assert resolve_disposition(DispositionContext(final_state=state)) == expected


def test_future_global_interrupts_are_not_call_states():
    """spec §3.1's global interrupts this phase doesn't yet drive must stay a distinct
    namespace from CallState — they're reserved signal names, not states this workflow
    transitions into."""
    call_state_values = {m.value for m in CallState}
    assert FUTURE_GLOBAL_INTERRUPTS.isdisjoint(call_state_values)


def test_future_global_interrupts_matches_spec_minus_phase1_handled():
    """spec §3.1 lists 13 global interrupts; Phase 1's CallSessionWorkflow handles
    CALL_DROPPED, HUMAN_REQUEST, SYSTEM_DATA_UNAVAILABLE, RUNTIME_COMPONENT_FAILURE itself
    (not via this reserved set) — the remaining 9 are what's reserved for later phases."""
    assert {
        "RECORDING_CONSENT_REFUSED",
        "COMMUNICATION_SUPPRESSION_REQUEST",
        "ACCESSIBILITY_REQUIREMENT_DETECTED",
        "DSAR_OR_PRIVACY_RIGHTS_REQUEST",
        "ADVERSARIAL_INPUT_DETECTED",
        "CUSTOMER_VULNERABILITY_INDICATED",
        "FRAUD_SUSPECTED",
        "LEGAL_SENSITIVITY_DETECTED",
        "SAFETY_OR_SECURITY_ESCALATION",
    } == FUTURE_GLOBAL_INTERRUPTS


def test_max_call_session_seconds_is_a_sane_bounded_ttl():
    """spec §4.1's bounded-TTL requirement for the distributed voice lock — must be
    positive and short enough to actually bound a hung workflow, not effectively unbounded."""
    assert 0 < MAX_CALL_SESSION_SECONDS <= 3600
