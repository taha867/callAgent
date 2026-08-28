"""CallSessionWorkflow — the Master Call State Machine, spec §3. Real implementation
replacing the Phase 0 stub. One workflow execution per call attempt,
`workflow_id = f"call-session-{customer_id}"` (set by the caller — campaigns/workflows.py's
RetrySchedulerWorkflow, or an ad-hoc POST /calls) — this is the distributed voice lock
(spec §4.1): Temporal rejects a second concurrent execution with that ID, no separate lock
table. See .claude/specs/phase-1-backend-spec.md decisions 0.1/0.2/0.5.

Signals in, activities out (decision 0.5): every inbound conversational event is a Temporal
signal, matching spec §3.1's global interrupts being inherently async/can-arrive-anytime.
The Phase 1 fake/text harness (tests/integration/test_phase1_e2e.py) drives this workflow by
sending signals directly — the exact same signal surface Phase 2's real voice/pipeline.py
will call into once STT/LLM/TTS exist, so none of this file's decision logic needs to change
then (this phase's Goal, phases/phase-1-deterministic-core.md).
"""

from datetime import datetime, timedelta
from typing import Literal

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporalio.workflow import ParentClosePolicy

    from src.actions.constants import ActionCode
    from src.calls import activities as calls_activities
    from src.calls.constants import CallState
    from src.calls.disposition import DispositionContext, resolve_disposition
    from src.calls.schemas import CallSessionInput, CallSessionOutput, CustomerIntentSignal
    from src.complaints.workflows import ComplaintSlaMonitorInput, ComplaintSlaMonitorWorkflow
    from src.verification.constants import MAX_AUTH_ATTEMPTS

_ACTIVITY_TIMEOUT = timedelta(seconds=10)
_BACKEND_ACTIVITY_TIMEOUT = timedelta(seconds=5)
_BACKEND_RETRY_POLICY = RetryPolicy(maximum_attempts=3)
_SIGNAL_WAIT_TIMEOUT = timedelta(minutes=5)


def _now():
    """workflow.now() is timezone-aware (UTC); every DateTime column in this codebase is
    naive TIMESTAMP WITHOUT TIME ZONE (the Phase 0 convention — see e.g.
    verification/service.py, complaints/service.py). Strip tzinfo here, once, rather than
    at every call site."""
    return workflow.now().replace(tzinfo=None)


@workflow.defn
class CallSessionWorkflow:
    def __init__(self) -> None:
        self._state = CallState.CALL_QUEUED
        self._pending_signals: list[CustomerIntentSignal] = []
        self._call_dropped = False
        self._action_sequence = 0
        # Phase 2, spec §8.9 — set by voice/dtmf.py's low-confidence-STT counter, a
        # cross-cutting interrupt handled the same way as _call_dropped (§0.4 of
        # .claude/specs/phase-2-backend-spec.md): every _wait_for_signal-based stage checks
        # it, not just one.
        self._dtmf_fallback_action: Literal["CALLBACK", "HUMAN"] | None = None

        # Facts accumulated as the call progresses — read once, at finalization, to build
        # the DispositionContext and the CallAttempt outcome record (spec §23).
        self._customer_reached = False
        self._right_party: bool | None = None
        self._was_authenticated = False
        self._verification_level: str | None = None
        self._status_delivered_key: str | None = None
        self._resolution: str | None = None

    # --- signals / queries --------------------------------------------------------------

    @workflow.signal
    async def customer_utterance(self, intent: CustomerIntentSignal) -> None:
        self._pending_signals.append(intent)

    @workflow.signal
    async def otp_response(self, code: str) -> None:
        self._pending_signals.append(CustomerIntentSignal(intent="OTP_ANSWER", value=code))

    @workflow.signal
    async def human_request_detected(self) -> None:
        self._pending_signals.append(CustomerIntentSignal(intent="REQUEST_HUMAN"))

    @workflow.signal
    async def call_dropped(self) -> None:
        self._call_dropped = True

    @workflow.signal
    async def dtmf_fallback(self, action: Literal["CALLBACK", "HUMAN"]) -> None:
        """spec §8.9 — voice/dtmf.py fires this after MAX_CONSECUTIVE_LOW_STT_TURNS, never
        the customer's own words (this is a deterministic system decision, unlike every
        other signal here, which is why it is its own signal and not a CustomerIntentSignal
        variant)."""
        self._dtmf_fallback_action = action

    @workflow.query
    def current_state(self) -> str:
        return self._state

    @workflow.query
    def current_verification_level(self) -> str:
        """spec §36 rule 1 — the one piece of call state voice/pipeline.py must never infer
        or accept from the LLM; it always asks the workflow. See
        .claude/specs/phase-2-backend-spec.md §0.3/§4.1."""
        return self._verification_level or "L0"

    # --- helpers --------------------------------------------------------------------------

    async def _wait_for_signal(
        self, wait_timeout: timedelta = _SIGNAL_WAIT_TIMEOUT
    ) -> CustomerIntentSignal | None:
        """Returns the next queued signal, or None if the call dropped, DTMF fallback
        activated, or nothing arrived within `wait_timeout`. A list, not a single Optional
        slot — two signals arriving with no `await` in between (e.g. customer_utterance
        immediately followed by call_dropped) must both be observable, never silently
        overwrite each other. A signal already queued when DTMF fires still wins — the flag
        is only consulted once the queue is empty, same precedence _call_dropped already
        has."""
        try:
            await workflow.wait_condition(
                lambda: (
                    bool(self._pending_signals)
                    or self._call_dropped
                    or self._dtmf_fallback_action is not None
                ),
                timeout=wait_timeout,
            )
        except TimeoutError:
            return None
        if not self._pending_signals:
            return None  # woken by call_dropped/dtmf_fallback with nothing queued
        return self._pending_signals.pop(0)

    def _next_action_key(self, call_id: str) -> str:
        """spec §10.6.4's Idempotency-Key shape, verbatim: `{call_id}-ACTION-{sequence}`.
        Incremented only here, inside the main workflow coroutine — never from a signal
        handler, which could race against this and break replay determinism (see
        .claude/specs/phase-1-backend-implementation-plan.md Batch 11)."""
        self._action_sequence += 1
        return f"{call_id}-ACTION-{self._action_sequence}"

    async def _finalize(
        self, inp: CallSessionInput, attempt_id: str, *, final_state: CallState, **flags
    ) -> CallSessionOutput:
        ctx = DispositionContext(
            final_state=final_state, was_authenticated=self._was_authenticated, **flags
        )
        disposition = resolve_disposition(ctx)

        await workflow.execute_activity(
            calls_activities.finalize_outcome,
            calls_activities.FinalizeOutcomeInput(
                call_attempt_id=attempt_id,
                disposition_code=disposition.value,
                answer_result=inp.simulated_answer_result,
                customer_reached=self._customer_reached,
                right_party=self._right_party,
                verified=self._was_authenticated,
                verification_level=self._verification_level,
                status_delivered=self._status_delivered_key,
                resolution=self._resolution or disposition.value,
            ),
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        await workflow.execute_activity(
            calls_activities.record_audit_event,
            calls_activities.RecordAuditEventInput(
                decision=final_state.value,
                reason_code=disposition.value,
                action_taken=disposition.value,
                call_id=attempt_id,
                correlation_id=inp.call_id,
                actor="SYSTEM",
            ),
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        return CallSessionOutput(call_id=inp.call_id, disposition_code=disposition.value)

    # --- run ------------------------------------------------------------------------------

    @workflow.run
    async def run(self, inp: CallSessionInput) -> CallSessionOutput:
        attempt_id = await workflow.execute_activity(
            calls_activities.create_call_attempt,
            calls_activities.CreateCallAttemptInput(
                call_id=inp.call_id,
                customer_id=inp.customer_id,
                claim_id=inp.claim_id,
                call_job_id=inp.call_job_id,
                attempt_number=inp.attempt_number,
                attempted_at=_now(),
            ),
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        self._state = CallState.DIALING

        answer_result = await workflow.execute_activity(
            calls_activities.classify_answer,
            calls_activities.ClassifyAnswerInput(
                call_id=inp.call_id, simulated_answer_result=inp.simulated_answer_result
            ),
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )

        if answer_result != "HUMAN_ANSWERED":
            self._state = (
                CallState(answer_result) if answer_result in CallState else CallState.FAILED
            )
            self._resolution = "CONTACT_NOT_ESTABLISHED"
            return await self._finalize(inp, attempt_id, final_state=self._state)

        self._customer_reached = True
        self._state = CallState.HUMAN_ANSWERED
        call_session_id = await workflow.execute_activity(
            calls_activities.create_call_session,
            calls_activities.CreateCallSessionInput(
                call_attempt_id=attempt_id, state=CallState.RIGHT_PARTY_CHECK
            ),
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        self._state = CallState.RIGHT_PARTY_CHECK

        terminal = await self._run_right_party_check(inp, attempt_id, call_session_id)
        if terminal is not None:
            return terminal

        terminal = await self._run_authentication(inp, attempt_id, call_session_id)
        if terminal is not None:
            return terminal

        return await self._run_status_and_follow_up(inp, attempt_id, call_session_id)

    # --- stage: right-party check ----------------------------------------------------------

    async def _run_right_party_check(
        self, inp: CallSessionInput, attempt_id: str, call_session_id: str
    ) -> CallSessionOutput | None:
        """Loops rather than acting on the first signal that arrives — signals genuinely
        meant for a later stage (e.g. an AUTH_ANSWER queued slightly ahead of the
        RIGHT_PARTY_CONFIRMED it followed, an ordering asyncio.gather on the client side
        does not guarantee) must be ignored here, not misread as confirmation. Only an
        explicit RIGHT_PARTY_CONFIRMED — or a signal recognized as one of this stage's own
        terminal outcomes — ends the wait."""
        while True:
            signal = await self._wait_for_signal()

            if signal is None:
                if self._dtmf_fallback_action is not None:
                    return await self._handle_dtmf_fallback(inp, attempt_id)
                if self._call_dropped:
                    return await self._finalize(
                        inp, attempt_id, final_state=CallState.CLOSE, call_dropped=True
                    )
                self._right_party = False
                return await self._finalize(
                    inp, attempt_id, final_state=CallState.CUSTOMER_UNAVAILABLE
                )

            if signal.intent == "WRONG_PARTY":
                self._right_party = False
                return await self._finalize(inp, attempt_id, final_state=CallState.WRONG_PARTY)

            if signal.intent == "CUSTOMER_UNAVAILABLE":
                self._right_party = False
                return await self._finalize(
                    inp, attempt_id, final_state=CallState.CUSTOMER_UNAVAILABLE
                )

            if signal.intent == "CUSTOMER_DRIVING":
                await workflow.execute_activity(
                    calls_activities.schedule_callback,
                    calls_activities.ScheduleCallbackInput(
                        key=self._next_action_key(inp.call_id),
                        correlation_id=inp.call_id,
                        customer_id=inp.customer_id,
                        claim_id=inp.claim_id,
                        callback_window_start=_now(),
                        callback_window_end=_now() + timedelta(hours=2),
                        reason="CUSTOMER_DRIVING",
                    ),
                    start_to_close_timeout=_ACTIVITY_TIMEOUT,
                )
                self._resolution = "CALLBACK_SCHEDULED"
                return await self._finalize(
                    inp, attempt_id, final_state=CallState.CLOSE, callback_requested=True
                )

            if signal.intent == "REQUEST_HUMAN":
                return await self._escalate_to_human(
                    inp, attempt_id, reason="CUSTOMER_REQUESTED_HUMAN"
                )

            if signal.intent != "RIGHT_PARTY_CONFIRMED":
                continue  # not relevant to this stage yet — keep waiting

            self._right_party = True
            await workflow.execute_activity(
                calls_activities.update_call_session,
                calls_activities.UpdateCallSessionInput(
                    call_session_id=call_session_id,
                    right_party_confirmed=True,
                    state=CallState.AUTHENTICATION,
                ),
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )
            self._state = CallState.AUTHENTICATION
            return None

    async def _escalate_to_human(
        self,
        inp: CallSessionInput,
        attempt_id: str,
        *,
        reason: str,
        dtmf_fallback: bool = False,
    ) -> CallSessionOutput:
        await workflow.execute_activity(
            calls_activities.create_escalation,
            calls_activities.CreateEscalationInput(
                key=self._next_action_key(inp.call_id),
                correlation_id=inp.call_id,
                call_id=inp.call_id,
                reason=reason,
                context_snapshot={
                    "customer_verified": self._was_authenticated,
                    "verification_level": self._verification_level,
                    "claim_id": inp.claim_id,
                    "customer_intent": "SPEAK_TO_CLAIMS_AGENT",
                },
            ),
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        self._resolution = "HUMAN_TRANSFER"
        return await self._finalize(
            inp,
            attempt_id,
            final_state=CallState.CLOSE,
            human_transferred=True,
            dtmf_fallback=dtmf_fallback,
        )

    async def _handle_dtmf_fallback(
        self, inp: CallSessionInput, attempt_id: str
    ) -> CallSessionOutput:
        """spec §8.9 — reachable from every _wait_for_signal-based stage (§0.4 of
        .claude/specs/phase-2-backend-spec.md), the same way _call_dropped is. Always tags
        DTMF_FALLBACK_ACTIVATED on the disposition regardless of which of the two options
        the customer picked — distinct operational signal from an ordinary
        CALLBACK_REQUESTED/SUCCESS_HUMAN_TRANSFER ("this call needed a keypad fallback
        because voice recognition kept failing"), per spec §31's dashboard analytics intent.
        """
        await workflow.execute_activity(
            calls_activities.record_audit_event,
            calls_activities.RecordAuditEventInput(
                decision="DTMF_FALLBACK_ACTIVATED",
                reason_code="DTMF_FALLBACK_ACTIVATED",
                call_id=attempt_id,
                correlation_id=inp.call_id,
                actor="SYSTEM",
            ),
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        if self._dtmf_fallback_action == "HUMAN":
            return await self._escalate_to_human(
                inp, attempt_id, reason="DTMF_FALLBACK", dtmf_fallback=True
            )
        await workflow.execute_activity(
            calls_activities.schedule_callback,
            calls_activities.ScheduleCallbackInput(
                key=self._next_action_key(inp.call_id),
                correlation_id=inp.call_id,
                customer_id=inp.customer_id,
                claim_id=inp.claim_id,
                callback_window_start=_now(),
                callback_window_end=_now() + timedelta(hours=2),
                reason="DTMF_FALLBACK",
            ),
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        self._resolution = "CALLBACK_SCHEDULED"
        return await self._finalize(
            inp,
            attempt_id,
            final_state=CallState.CLOSE,
            dtmf_fallback=True,
            callback_requested=True,
        )

    # --- stage: authentication ------------------------------------------------------------

    async def _run_authentication(
        self, inp: CallSessionInput, attempt_id: str, call_session_id: str
    ) -> CallSessionOutput | None:
        factor_type = await workflow.execute_activity(
            calls_activities.get_configured_auth_factor_type,
            calls_activities.GetAuthFactorTypeInput(customer_id=inp.customer_id),
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )

        while True:
            signal = await self._wait_for_signal()

            if signal is None:
                if self._dtmf_fallback_action is not None:
                    return await self._handle_dtmf_fallback(inp, attempt_id)
                if self._call_dropped:
                    return await self._finalize(
                        inp, attempt_id, final_state=CallState.CLOSE, call_dropped=True
                    )
                return await self._finalize(inp, attempt_id, final_state=CallState.AUTH_FAILED)

            if signal.intent == "REQUEST_HUMAN":
                return await self._escalate_to_human(
                    inp, attempt_id, reason="CUSTOMER_REQUESTED_HUMAN"
                )

            if signal.intent == "REQUEST_OTP":
                terminal = await self._run_otp_challenge(inp, attempt_id, call_session_id)
                if terminal is not None:
                    return terminal
                return None  # OTP verified — Level 2 authenticated, proceed

            if signal.intent != "AUTH_ANSWER":
                continue  # not an auth-relevant signal in this state; keep waiting

            result = await workflow.execute_activity(
                calls_activities.verify_level1,
                calls_activities.VerifyLevel1Input(
                    call_id=attempt_id,
                    call_session_id=call_session_id,
                    customer_id=inp.customer_id,
                    factor_type=factor_type or "",
                    supplied_value=signal.value or "",
                    now=_now(),
                ),
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )

            if result.outcome == "MATCH":
                self._was_authenticated = True
                self._verification_level = "L1"
                await workflow.execute_activity(
                    calls_activities.update_call_session,
                    calls_activities.UpdateCallSessionInput(
                        call_session_id=call_session_id,
                        verification_level="L1",
                        state=CallState.AUTHENTICATED,
                    ),
                    start_to_close_timeout=_ACTIVITY_TIMEOUT,
                )
                self._state = CallState.AUTHENTICATED
                return None

            if result.attempts_so_far >= MAX_AUTH_ATTEMPTS:
                return await self._finalize(inp, attempt_id, final_state=CallState.AUTH_FAILED)
            # else: loop — ask again, spec §10.4's "let's try one other verification method"

    async def _run_otp_challenge(
        self, inp: CallSessionInput, attempt_id: str, call_session_id: str
    ) -> CallSessionOutput | None:
        phone = await workflow.execute_activity(
            calls_activities.get_customer_phone,
            calls_activities.GetCustomerPhoneInput(customer_id=inp.customer_id),
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        sent = await workflow.execute_activity(
            calls_activities.send_otp,
            calls_activities.SendOtpInput(
                call_id=attempt_id,
                call_session_id=call_session_id,
                phone_e164=phone,
                now=_now(),
            ),
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )

        while True:
            signal = await self._wait_for_signal()

            if signal is None:
                if self._dtmf_fallback_action is not None:
                    return await self._handle_dtmf_fallback(inp, attempt_id)
                if self._call_dropped:
                    return await self._finalize(
                        inp, attempt_id, final_state=CallState.CLOSE, call_dropped=True
                    )
                return await self._finalize(inp, attempt_id, final_state=CallState.AUTH_FAILED)

            if signal.intent == "REQUEST_HUMAN":
                return await self._escalate_to_human(
                    inp, attempt_id, reason="CUSTOMER_REQUESTED_HUMAN"
                )

            if signal.intent != "OTP_ANSWER":
                continue

            try:
                result = await workflow.execute_activity(
                    calls_activities.verify_otp,
                    calls_activities.VerifyOtpInput(
                        call_id=attempt_id,
                        challenge_id=sent.challenge_id,
                        supplied_code=signal.value or "",
                        now=_now(),
                    ),
                    start_to_close_timeout=_ACTIVITY_TIMEOUT,
                )
            except Exception:
                # the 15 exit-criteria branches; fail safe rather than hang the call.
                return await self._finalize(
                    inp, attempt_id, final_state=CallState.CLOSE, otp_locked=True
                )

            if result.status == "VERIFIED":
                self._was_authenticated = True
                self._verification_level = "L2"
                await workflow.execute_activity(
                    calls_activities.update_call_session,
                    calls_activities.UpdateCallSessionInput(
                        call_session_id=call_session_id,
                        verification_level="L2",
                        state=CallState.AUTHENTICATED,
                    ),
                    start_to_close_timeout=_ACTIVITY_TIMEOUT,
                )
                self._state = CallState.AUTHENTICATED
                return None

            if result.status == "LOCKED":
                return await self._finalize(
                    inp, attempt_id, final_state=CallState.CLOSE, otp_locked=True
                )
            # else: still "SENT" (wrong code, attempts remain) — loop and wait for retry

    # --- stage: status delivery + follow-up -------------------------------------------------

    async def _run_status_and_follow_up(
        self, inp: CallSessionInput, attempt_id: str, call_session_id: str
    ) -> CallSessionOutput:
        self._state = CallState.STATUS_DELIVERY
        status = None
        backend_unavailable = False
        try:
            status = await workflow.execute_activity(
                calls_activities.deliver_status,
                calls_activities.DeliverStatusInput(
                    call_id=attempt_id,
                    claim_id=inp.claim_id,
                    verification_level=self._verification_level or "L0",
                ),
                start_to_close_timeout=_BACKEND_ACTIVITY_TIMEOUT,
                retry_policy=_BACKEND_RETRY_POLICY,
            )
        except Exception:
            backend_unavailable = True

        if backend_unavailable or status is None:
            await workflow.execute_activity(
                calls_activities.create_action,
                calls_activities.CreateActionInput(
                    key=self._next_action_key(inp.call_id),
                    correlation_id=inp.call_id,
                    claim_id=inp.claim_id,
                    action_code="BACKEND_DATA_VERIFICATION_REQUEST",
                    summary="Status delivery unavailable — backend dependency failure",
                    source_call_id=attempt_id,
                ),
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )
            self._resolution = "BACKEND_SYSTEM_FAILURE"
            return await self._finalize(
                inp, attempt_id, final_state=CallState.CLOSE, backend_unavailable=True
            )

        self._status_delivered_key = status.approved_customer_message_key
        await workflow.execute_activity(
            calls_activities.update_call_session,
            calls_activities.UpdateCallSessionInput(
                call_session_id=call_session_id,
                status_already_disclosed=True,
                state=CallState.FOLLOW_UP,
            ),
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
        )
        self._state = CallState.FOLLOW_UP

        signal = await self._wait_for_signal()

        if signal is None:
            if self._dtmf_fallback_action is not None:
                return await self._handle_dtmf_fallback(inp, attempt_id)
            if self._call_dropped:
                return await self._finalize(
                    inp,
                    attempt_id,
                    final_state=CallState.CLOSE,
                    call_dropped=True,
                    status_delivered=True,
                )
            self._resolution = "FULLY_RESOLVED_BY_AI"
            return await self._finalize(
                inp, attempt_id, final_state=CallState.CLOSE, status_delivered=True
            )

        if signal.intent == "NOTHING_ELSE":
            self._resolution = "FULLY_RESOLVED_BY_AI"
            return await self._finalize(
                inp, attempt_id, final_state=CallState.CLOSE, status_delivered=True
            )

        if signal.intent == "ASK_QUESTION":
            # Grounded answer: the answer is the structured field itself (spec §14 Type A/B)
            # — Phase 1 has no LLM to phrase it, the activity's already-fetched claim data
            # IS the answer. No separate activity call needed; status already carries it.
            self._resolution = "FULLY_RESOLVED_BY_AI"
            return await self._finalize(
                inp,
                attempt_id,
                final_state=CallState.CLOSE,
                status_delivered=True,
                question_resolved=True,
            )

        if signal.intent == "DISPUTE_DOCUMENT":
            await workflow.execute_activity(
                calls_activities.create_action,
                calls_activities.CreateActionInput(
                    key=self._next_action_key(inp.call_id),
                    correlation_id=inp.call_id,
                    claim_id=inp.claim_id,
                    action_code="DOCUMENT_STATUS_DISPUTE",
                    summary=signal.summary or f"Customer disputes status of {signal.document_type}",
                    source_call_id=attempt_id,
                ),
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )
            self._resolution = "ACTION_CREATED"
            return await self._finalize(
                inp,
                attempt_id,
                final_state=CallState.CLOSE,
                status_delivered=True,
                action_created=True,
            )

        if signal.intent == "DISSATISFIED":
            await workflow.execute_activity(
                calls_activities.create_action,
                calls_activities.CreateActionInput(
                    key=self._next_action_key(inp.call_id),
                    correlation_id=inp.call_id,
                    claim_id=inp.claim_id,
                    action_code="CLAIM_DELAY_ESCALATION",
                    summary=signal.summary or "Customer dissatisfied with delay",
                    source_call_id=attempt_id,
                ),
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )
            self._resolution = "ACTION_CREATED"
            return await self._finalize(
                inp,
                attempt_id,
                final_state=CallState.CLOSE,
                status_delivered=True,
                action_created=True,
            )

        if signal.intent == "COMPLAINT_REQUEST":
            complaint = await workflow.execute_activity(
                calls_activities.create_complaint,
                calls_activities.CreateComplaintInput(
                    key=self._next_action_key(inp.call_id),
                    correlation_id=inp.call_id,
                    claim_id=inp.claim_id,
                    source_call_id=attempt_id,
                    complaint_category=signal.complaint_category or "CLAIM_DELAY",
                    customer_statement_summary=signal.summary
                    or "Customer requests formal complaint",
                    severity=signal.severity or "MEDIUM",
                    preferred_contact_method="PHONE",
                    now=_now(),
                ),
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )
            # ABANDON: the SLA clock (spec §18.1) must keep running long after this call
            # (and this workflow) completes — see complaints/workflows.py's module docstring.
            await workflow.start_child_workflow(
                ComplaintSlaMonitorWorkflow.run,
                ComplaintSlaMonitorInput(
                    complaint_id=complaint["id"],
                    claim_id=inp.claim_id,
                    acknowledgment_due_at=datetime.fromisoformat(
                        complaint["acknowledgment_due_at"]
                    ),
                    resolution_due_at=datetime.fromisoformat(complaint["resolution_due_at"]),
                ),
                id=f"complaint-sla-{complaint['id']}",
                parent_close_policy=ParentClosePolicy.ABANDON,
            )
            self._resolution = "COMPLAINT_REGISTERED"
            return await self._finalize(
                inp,
                attempt_id,
                final_state=CallState.CLOSE,
                status_delivered=True,
                complaint_created=True,
            )

        if signal.intent == "REQUEST_HUMAN":
            return await self._escalate_to_human(inp, attempt_id, reason="CUSTOMER_REQUESTED_HUMAN")

        # --- Phase 2: AI-initiated tool calls bridged from voice/tools.py's dispatch table
        # (.claude/specs/phase-2-backend-spec.md §0.3/§4.2) — the LLM decided one of these
        # side-effecting actions was appropriate; the workflow still owns executing it and
        # deciding the resulting disposition, per CLAUDE.md's Shape B ("the workflow — not
        # the model — decides"). `signal.topic`'s validity (a real ActionCode/link type) is
        # voice/tools.py's responsibility at dispatch time, same trust level this file
        # already gives every other literal action_code string below.

        if signal.intent == "AI_SCHEDULE_CALLBACK":
            await workflow.execute_activity(
                calls_activities.schedule_callback,
                calls_activities.ScheduleCallbackInput(
                    key=self._next_action_key(inp.call_id),
                    correlation_id=inp.call_id,
                    customer_id=inp.customer_id,
                    claim_id=inp.claim_id,
                    callback_window_start=signal.callback_window_start or _now(),
                    callback_window_end=signal.callback_window_end or (_now() + timedelta(hours=2)),
                    reason=signal.summary or "AI_INITIATED_CALLBACK",
                ),
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )
            self._resolution = "CALLBACK_SCHEDULED"
            return await self._finalize(
                inp,
                attempt_id,
                final_state=CallState.CLOSE,
                status_delivered=True,
                callback_requested=True,
            )

        if signal.intent == "AI_CREATE_ACTION":
            await workflow.execute_activity(
                calls_activities.create_action,
                calls_activities.CreateActionInput(
                    key=self._next_action_key(inp.call_id),
                    correlation_id=inp.call_id,
                    claim_id=inp.claim_id,
                    action_code=signal.topic or ActionCode.CLAIMS_TEAM_QUERY.value,
                    summary=signal.summary or "AI-initiated action",
                    source_call_id=attempt_id,
                ),
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )
            self._resolution = "ACTION_CREATED"
            return await self._finalize(
                inp,
                attempt_id,
                final_state=CallState.CLOSE,
                status_delivered=True,
                action_created=True,
            )

        if signal.intent == "AI_SEND_SECURE_LINK":
            await workflow.execute_activity(
                calls_activities.send_secure_link,
                calls_activities.SendSecureLinkInput(
                    key=self._next_action_key(inp.call_id),
                    correlation_id=inp.call_id,
                    claim_id=inp.claim_id,
                    customer_id=inp.customer_id,
                    link_type=signal.topic or "GENERAL",
                    source_call_id=attempt_id,
                ),
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
            )
            self._resolution = "ACTION_CREATED"
            return await self._finalize(
                inp,
                attempt_id,
                final_state=CallState.CLOSE,
                status_delivered=True,
                action_created=True,
            )

        # Unrecognized intent in this state — treat as "nothing else," matching spec §14
        # Type D's "do not hallucinate an answer" for anything genuinely out of scope.
        self._resolution = "FULLY_RESOLVED_BY_AI"
        return await self._finalize(
            inp, attempt_id, final_state=CallState.CLOSE, status_delivered=True
        )
