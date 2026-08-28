"""resolve_disposition — a pure function, no I/O, table-driven over CallState + a small set
of already-decided facts. Called once, by CallSessionWorkflow's final activity, per spec
§0.9's design (see .claude/specs/phase-1-backend-spec.md §9).

`DispositionContext.final_state` is the last *meaningful* state CallSessionWorkflow reached
before transitioning to Close, not always literally CallState.CLOSE — spec §3's diagram
formally routes every terminal branch (WrongParty, AuthFailed, ...) through Close, but Close
itself carries no information, so the workflow passes whichever state was meaningful (e.g.
CallState.WRONG_PARTY) as `final_state` and this resolver treats CallState.CLOSE as meaning
specifically "the successful/action/complaint/escalation family," disambiguated by the
boolean context fields.

DispositionCode.CONCURRENT_CALL_CONFLICT is NOT produced by this function — a concurrent-
call conflict means CallSessionWorkflow never started/ran at all (RetrySchedulerWorkflow's
own ChildWorkflowError/WorkflowAlreadyStartedError handling produces that disposition
directly, spec §10.1) — there is no CallState for a workflow execution that never began.

This module imports only `pydantic` and `src.calls.constants` — same "workflow-sandbox-safe"
discipline calls/constants.py's own docstring already establishes, since CallSessionWorkflow
(Batch 11) calls this directly from inside sandboxed workflow code, not from an activity.
"""

from pydantic import BaseModel

from src.calls.constants import CallState, DispositionCode


class DispositionContext(BaseModel):
    """Carries only already-decided facts — never re-derives anything from raw signal
    history. resolve_disposition does a single pure match over this, no side effects."""

    final_state: CallState
    status_delivered: bool = False
    question_resolved: bool = False
    complaint_created: bool = False
    action_created: bool = False
    human_transferred: bool = False
    callback_requested: bool = False
    otp_locked: bool = False
    otp_attempts_exceeded: bool = False
    call_dropped: bool = False
    was_authenticated: bool = False
    backend_unavailable: bool = False
    dtmf_fallback: bool = False  # spec §8.9, Phase 2


class UnresolvedDispositionError(Exception):
    """Raised when no rule below matches — deliberately never raised in production use.
    Exists so tests/unit/test_disposition_resolution.py can assert every CallState this
    workflow can actually reach as a terminal final_state has a matching rule; a new
    terminal CallState added later without a matching disposition rule fails a unit test
    immediately, not silently at runtime."""

    def __init__(self, ctx: DispositionContext) -> None:
        self.ctx = ctx
        super().__init__(f"no disposition rule matched: {ctx!r}")


def resolve_disposition(ctx: DispositionContext) -> DispositionCode:
    # Interrupt-style outcomes are checked FIRST, before final_state resolution — a call
    # drop, an OTP lockout, or a backend failure must always win the disposition even if a
    # best-effort fallback action (e.g. BACKEND_DATA_VERIFICATION_REQUEST, spec §14 Type E)
    # also got created along the way and would otherwise set action_created=True. These are
    # not "the state the call ended in," they're "why the call ended the way it did."
    if ctx.call_dropped:
        return (
            DispositionCode.CALL_DROPPED_PRE_AUTH
            if not ctx.was_authenticated
            else DispositionCode.CALL_DROPPED_POST_AUTH
        )
    if ctx.otp_locked:
        return DispositionCode.OTP_LOCKED
    if ctx.otp_attempts_exceeded:
        return DispositionCode.OTP_ATTEMPTS_EXCEEDED
    if ctx.backend_unavailable:
        return DispositionCode.BACKEND_SYSTEM_FAILURE
    if ctx.dtmf_fallback:
        return DispositionCode.DTMF_FALLBACK_ACTIVATED

    match ctx.final_state:
        case CallState.NO_ANSWER:
            return DispositionCode.NO_ANSWER
        case CallState.VOICEMAIL:
            return DispositionCode.VOICEMAIL
        case CallState.FAILED:
            return DispositionCode.NETWORK_FAILURE
        case CallState.WRONG_PARTY:
            return DispositionCode.WRONG_PARTY
        case CallState.CUSTOMER_UNAVAILABLE:
            return DispositionCode.RIGHT_PARTY_NOT_AVAILABLE
        case CallState.AUTH_FAILED:
            return DispositionCode.AUTH_FAILED
        # Ordered most-specific-outcome-wins, NOT status-first: in the actual workflow,
        # status is always delivered before the follow-up stage that creates an action/
        # complaint/escalation/callback, so status_delivered=True co-occurs with those flags
        # on every such call. Checking status_delivered first would shadow the more notable
        # outcome and always report plain "status delivered" — wrong. callback_requested
        # joins this tier as of Phase 2's AI_SCHEDULE_CALLBACK branch (spec's own tool-
        # dispatch bridge), which — unlike Phase 1's pre-status-delivery CUSTOMER_DRIVING
        # branch — can fire after status_delivered=True is already set; it was originally a
        # bottom-of-function-only fallback because that combination never previously arose.
        case CallState.CLOSE if ctx.human_transferred:
            return DispositionCode.SUCCESS_HUMAN_TRANSFER
        case CallState.CLOSE if ctx.complaint_created:
            return DispositionCode.SUCCESS_COMPLAINT_REGISTERED
        case CallState.CLOSE if ctx.action_created:
            return DispositionCode.SUCCESS_ACTION_CREATED
        case CallState.CLOSE if ctx.callback_requested:
            return DispositionCode.CALLBACK_REQUESTED
        case CallState.CLOSE if ctx.status_delivered and ctx.question_resolved:
            return DispositionCode.SUCCESS_STATUS_AND_QUERY_RESOLVED
        case CallState.CLOSE if ctx.status_delivered:
            return DispositionCode.SUCCESS_STATUS_DELIVERED

    # Lowest priority: a plain callback request on a non-CLOSE final_state (there is no
    # such case today, but this stays as a defensive fallback, same reasoning as the rest
    # of this function's "never silently guess" discipline).
    if ctx.callback_requested:
        return DispositionCode.CALLBACK_REQUESTED

    raise UnresolvedDispositionError(ctx)
