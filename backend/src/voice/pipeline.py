"""The Pipecat pipeline assembly — spec §2.2's diagram: STT -> guard/DTMF tap -> LLM
tool-use (bridged into the running CallSessionWorkflow) -> TTS. Replaces Phase 1's fake/text
harness with the real thing while calling into the exact same Temporal signal surface
(.claude/specs/phase-2-backend-spec.md §0.1 / phase-1-backend-spec.md decision 0.5) — no
workflow-side code changes were needed to make this connection.

Every STT/LLM/TTS/telephony component here comes from voice/adapters/* (config-driven,
swappable per CLAUDE.md §2.7); this module never imports a vendor SDK directly. Latency
telemetry is Pipecat's own native tracing (voice/telemetry.py), not hand-rolled spans.
"""

from typing import Any, cast

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import Frame, InputDTMFFrame, TranscriptionFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.base_transport import BaseTransport
from pipecat.workers.runner import WorkerRunner
from temporalio.client import Client, WorkflowHandle

from src.voice import dtmf, guard
from src.voice.adapters.llm import get_llm_service
from src.voice.adapters.stt import get_stt_service
from src.voice.adapters.tts import get_tts_service
from src.voice.config import voice_settings
from src.voice.prompt import PromptContext, build_system_prompt
from src.voice.tools import TOOL_REGISTRY, dispatch_tool_call


class CallPipelineContext:
    """Per-call, in-memory scratch state — never persisted. Spec §10.6.2's recovery-state
    scope is "within the same live telephony session" only; a dropped/reconnected call
    starts a brand-new CallSessionWorkflow execution AND a brand-new pipeline context by
    construction (phase-1-backend-spec.md §3.2's "no separate resume code path" note applies
    here identically)."""

    def __init__(
        self,
        *,
        call_id: str,
        customer_id: str,
        claim_id: str,
        workflow_handle: WorkflowHandle,
    ) -> None:
        self.call_id = call_id
        self.customer_id = customer_id
        self.claim_id = claim_id
        self.workflow_handle = workflow_handle
        self.current_language = "en"
        self.adversarial_streak = 0


async def _fetch_claim_and_customer(ctx: CallPipelineContext) -> tuple[Any, Any]:
    from src.claims import service as claims_service
    from src.customers.models import Customer
    from src.database import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as session:
        claim = await claims_service.get_claim(session, ctx.claim_id)
        customer = await session.get(Customer, ctx.customer_id)
        return claim, customer


async def _build_prompt_context(ctx: CallPipelineContext) -> PromptContext:
    """spec §36 rule 1 — verification_level always comes from the workflow's own query,
    never cached or inferred here. claim_stage/customer_first_name are read directly (the
    same DB access voice/tools.py's read tools already need — CLAUDE.md's Shape B diagram
    boundary is "the LLM never touches the DB directly," not this module)."""
    from src.calls.workflows import CallSessionWorkflow

    verification_level = await ctx.workflow_handle.query(
        CallSessionWorkflow.current_verification_level
    )
    claim, customer = await _fetch_claim_and_customer(ctx)
    return PromptContext(
        claim_stage=claim.claim_stage.value if claim else "UNKNOWN",
        verification_level=verification_level,
        language=ctx.current_language,
        next_expected_event=claim.next_expected_event if claim else None,
        customer_first_name=customer.full_name.split(" ")[0] if customer else None,
    )


def _make_tool_handler(tool_name: str, ctx: CallPipelineContext):
    async def _handler(params: FunctionCallParams) -> None:
        result = await dispatch_tool_call(
            name=tool_name,
            args=dict(params.arguments),
            call_id=ctx.call_id,
            workflow_handle=ctx.workflow_handle,
        )
        await params.result_callback(result)

    return _handler


def _build_tool_schemas(ctx: CallPipelineContext) -> list[Any]:
    """Translates TOOL_REGISTRY (the CI-checked allow-list, spec §2.2.2 rule 3) into
    Pipecat's own function-calling shape — TOOL_REGISTRY stays the single source of truth;
    Pipecat is only the transport that invokes dispatch_tool_call's handlers. Returns
    `list[Any]` rather than `list[FunctionSchema]` only to satisfy LLMContext(tools=...)'s
    invariant list typing against its broader `FunctionSchema | Callable` element type —
    every element here is still a real `FunctionSchema`."""
    schemas: list[Any] = []
    for name, spec in TOOL_REGISTRY.items():
        json_schema = spec.args_schema.model_json_schema()
        schemas.append(
            FunctionSchema(
                name=name,
                description=spec.description,
                properties=json_schema.get("properties", {}),
                required=json_schema.get("required", []),
                handler=_make_tool_handler(name, ctx),
            )
        )
    return schemas


class _ConversationTapProcessor(FrameProcessor):
    """Sits between STT and the LLM context aggregator. Never drops or alters a frame it
    doesn't itself act on (CLAUDE.md's custom-FrameProcessor discipline; spec §2.2.2 rule 5
    — detection is a signal source only, never a state transition by itself).

    On every non-empty transcription: resets the DTMF low-confidence counter, tags
    adversarial input (spec §2.2.2), persists a detected language change (spec §2.2.3), and
    refreshes the LLM's system prompt with the current verification_level/claim context —
    always re-queried from the workflow, never cached across a turn.

    On an empty transcription: increments the low-confidence counter (spec §8.9). Whisper's
    TranscriptionFrame carries no numeric confidence score — confirmed via direct
    `pipecat-ai` package introspection, WhisperSTTService filters by `no_speech_prob`
    internally before ever emitting a frame — so "VAD detected speech but STT produced no
    text" is the real, available signal for a low-confidence turn, not a threshold on a
    confidence field that doesn't exist on the frame. This should be reconfirmed against
    real audio during the Phase 2 manual smoke test (spec §12) — CI cannot exercise it.

    Consumes InputDTMFFrame directly (not Pipecat's DTMFAggregator — unnecessary for a
    single-digit response) to resolve a pending fallback once triggered.
    """

    def __init__(self, ctx: CallPipelineContext, llm_context: LLMContext, **kwargs) -> None:
        super().__init__(**kwargs)
        self._ctx = ctx
        self._llm_context = llm_context
        self._fallback_pending = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, InputDTMFFrame) and self._fallback_pending:
            self._fallback_pending = False
            await self._resolve_dtmf(frame.button.value)
            return  # a keypad press is not a conversational transcript

        if isinstance(frame, TranscriptionFrame):
            if frame.text.strip():
                dtmf.reset_counter(self._ctx.call_id)
                await self._on_real_transcription(frame)
            else:
                await self._on_empty_transcription()

        await self.push_frame(frame, direction)

    async def _resolve_dtmf(self, digit: str) -> None:
        from src.calls.workflows import CallSessionWorkflow

        action = dtmf.resolve_dtmf_action(digit)
        await self._ctx.workflow_handle.signal(CallSessionWorkflow.dtmf_fallback, action)

    async def _on_real_transcription(self, frame: TranscriptionFrame) -> None:
        if frame.language and str(frame.language) != self._ctx.current_language:
            await self._persist_language(str(frame.language))
        await self._refresh_system_prompt()
        await self._tag_if_adversarial(frame.text)

    async def _tag_if_adversarial(self, text: str) -> None:
        result = guard.classify_adversarial(text)
        if not result.is_adversarial:
            return

        from src.calls.activities import RecordAuditEventInput, record_audit_event
        from src.calls.workflows import CallSessionWorkflow

        await record_audit_event(
            RecordAuditEventInput(
                decision="ADVERSARIAL_INPUT_TAGGED",
                reason_code="ADVERSARIAL_INPUT_DETECTED",
                call_id=self._ctx.call_id,
                correlation_id=self._ctx.call_id,
                actor="AI",
            )
        )
        self._ctx.adversarial_streak += 1
        if self._ctx.adversarial_streak >= voice_settings.MAX_ADVERSARIAL_STREAK:
            # spec §2.2.2 rule 9 — persistent adversarial input escalates to a human, via
            # the existing human_request_detected() path, never a new escalation mechanism.
            await self._ctx.workflow_handle.signal(CallSessionWorkflow.human_request_detected)

    async def _on_empty_transcription(self) -> None:
        count = dtmf.register_low_confidence_turn(self._ctx.call_id)
        if count < voice_settings.MAX_CONSECUTIVE_LOW_STT_TURNS:
            return
        dtmf.reset_counter(self._ctx.call_id)
        self._fallback_pending = True
        # Deterministic, pre-scripted text — never an LLM-generated filler (spec §8.9).
        await self.push_frame(TTSSpeakFrame(dtmf.fallback_prompt(self._ctx.current_language)))

    async def _persist_language(self, language: str) -> None:
        self._ctx.current_language = language

        from sqlalchemy import select

        from src.calls import service as calls_service
        from src.calls.models import CallSession
        from src.database import get_session_factory

        session_factory = get_session_factory()
        async with session_factory() as session, session.begin():
            result = await session.execute(
                select(CallSession.id).where(CallSession.call_attempt_id == self._ctx.call_id)
            )
            call_session_id = result.scalar_one_or_none()
            if call_session_id is None:
                return  # HUMAN_ANSWERED hasn't created a CallSession row yet
            await calls_service.update_call_session_language(
                session, call_session_id=call_session_id, language=language
            )

    async def _refresh_system_prompt(self) -> None:
        prompt_context = await _build_prompt_context(self._ctx)
        system_prompt = build_system_prompt(prompt_context)
        # LLMContext's typed message union covers every provider-specific message shape;
        # every message this module ever puts in is a plain dict (never an
        # LLMSpecificMessage), so a cast here is accurate, not just a type-checker silencer.
        messages = cast("list[dict[str, Any]]", self._llm_context.get_messages())
        if messages and messages[0].get("role") == "system":
            messages[0]["content"] = system_prompt
        else:
            messages.insert(0, {"role": "system", "content": system_prompt})
        self._llm_context.set_messages(cast(Any, messages))


async def run_call_pipeline(
    *, call_id: str, customer_id: str, claim_id: str, transport: BaseTransport, client: Client
) -> None:
    """The browser-demo entry point voice_server.py's offer handler calls once per accepted
    WebRTC connection. `workflow_id` matches campaigns/workflows.py's and calls/router.py's
    own convention exactly — this is the distributed voice lock (spec §4.1), unchanged."""
    from src.calls.workflows import CallSessionWorkflow

    workflow_handle = client.get_workflow_handle_for(
        CallSessionWorkflow.run, workflow_id=f"call-session-{customer_id}"
    )
    ctx = CallPipelineContext(
        call_id=call_id, customer_id=customer_id, claim_id=claim_id, workflow_handle=workflow_handle
    )

    claim, _ = await _fetch_claim_and_customer(ctx)
    if claim is not None:
        ctx.current_language = claim.language  # spec §2.2.3's initial preference

    initial_system_prompt = build_system_prompt(await _build_prompt_context(ctx))
    llm_context = LLMContext(
        messages=[{"role": "system", "content": initial_system_prompt}],
        tools=_build_tool_schemas(ctx),
    )

    stt = get_stt_service()
    tts = get_tts_service(language=ctx.current_language)
    llm = get_llm_service()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        llm_context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer())
    )
    tap = _ConversationTapProcessor(ctx, llm_context)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            tap,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )
    worker = PipelineWorker(
        pipeline,
        enable_tracing=True,
        additional_span_attributes={"call.id": call_id, "customer.id": customer_id},
        conversation_id=call_id,
    )
    runner = WorkerRunner()
    await runner.run(worker)
