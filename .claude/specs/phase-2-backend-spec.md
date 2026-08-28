# Phase 2 — Backend Engineering Spec (Conversation Layer)

**Status:** Draft — ready for implementation
**Depends on:** [`phase-1-backend-spec.md`](./phase-1-backend-spec.md) (implemented, commit `eeb64cf`)
**Spec references:** §2.2 (Conversational AI Layer), §2.2.1 (Latency/Dead-Air), §2.2.2 (Prompt
Injection Defense), §2.2.3 (Language/Code-Switching), §8.9 (DTMF Fallback), §10.6.1 (Model/
STT/TTS Failure), §21 (AI Authority Matrix), §36 rules 1/3/4/13/14/21/29/35, Demo 1 & Demo 4
(§29)
**Code-shape references:** `CLAUDE.md` §2.6 (Temporal), §2.7 (Voice pipeline & vendor
adapters), §2.8 (Settings)
**Phase file:** [`phases/phase-2-conversation-layer.md`](../../phases/phase-2-conversation-layer.md)
**Tech stack (demo tier):** `IMPLEMENTATION_PLAN.md` §1 — Pipecat, faster-whisper or Groq's
free-tier hosted Whisper (STT), Piper (TTS), Gemini/Groq free tier (LLM, function-calling
capable), browser WebRTC (telephony transport)

---

## 0. Design decisions (read this before implementing)

### 0.1 `voice_server.py` is a third deployable process — a Temporal *client*, never a worker or a router

`CLAUDE.md` §2.1 already names three processes: `main.py` (HTTP API), `worker.py` (Temporal
worker), `voice_server.py` (Pipecat real-time server). Phase 1 built the first two;
`voice_server.py` doesn't exist yet — it is entirely this phase's work. Its relationship to
`CallSessionWorkflow` is **client, not host**: `voice_server.py` calls
`Client.connect(settings.TEMPORAL_HOST, ...)` (the same call `worker.py` already makes) and
uses that client to `get_workflow_handle(workflow_id).signal(...)` / `.query(...)` against a
running `CallSessionWorkflow` execution — it never imports `workflow.defn`/`workflow.signal`
decorators itself, and it never registers with a `Worker`. This mirrors exactly how
`tests/integration/test_phase1_e2e.py` already drives the workflow (per
`phase-1-backend-spec.md` §0.5) — Phase 2 replaces that test harness's signal-sending code
with `voice/pipeline.py`'s signal-sending code, calling the identical
`workflow_id = f"call-session-{customer_id}"` convention `campaigns/workflows.py` and the ad
hoc `POST /calls` endpoint already use. **No workflow-side code changes** are required to
make this connection — this is the entire point of Phase 1's decision 0.5, now realized.

`voice_server.py` does need one workflow-side addition: a **query** to read back the call's
authoritative verification level and claim context before dispatching an LLM tool call (see
§4.1) — `CallSessionWorkflow.current_state()` already exists; this phase adds
`current_verification_level()` and `current_claim_context()` alongside it, following the
identical `@workflow.query` pattern.

### 0.2 Every vendor is a `Protocol` + provider module; nothing in `pipeline.py` imports a vendor SDK directly

Per `CLAUDE.md` §2.7, verbatim. Four adapter families, one `Protocol` each:

```
src/voice/adapters/
├── stt/base.py          # SpeechToTextAdapter.stream(audio: AsyncIterator[bytes]) -> AsyncIterator[Transcript]
├── tts/base.py          # TextToSpeechAdapter.synthesize(text: str) -> AsyncIterator[bytes]  (chunked/streaming)
├── llm/base.py           # ConversationLlmAdapter.complete(prompt, tools) -> LlmTurnResult (text | tool_call)
└── telephony/base.py     # TelephonyTransportAdapter — Pipecat transport factory, not a network client itself
```

`voice/config.py::VoiceConfig` names the active adapter per family (`STT_PROVIDER`,
`TTS_PROVIDER`, `LLM_PROVIDER`, `TELEPHONY_PROVIDER`) exactly as `CLAUDE.md` §2.7 sketches.
This is what makes the Phase 6 paid-vendor swap a config change — nothing this phase writes
should special-case a provider name outside `voice/config.py`'s factory function.

### 0.3 The tool-dispatch → signal bridge — the one genuinely new architectural piece this phase adds

Phase 0 built `voice/tools.py`'s `TOOL_REGISTRY` (13 entries) and `dispatch_tool_call()`,
which today validates args and raises `NotImplementedError`. Phase 2's job is to give each
of those 13 tools a real body — but **not** by having `dispatch_tool_call` call domain
services directly for anything that changes call state. `CLAUDE.md`'s Shape B diagram is
explicit: *"LLM tool-use call → Temporal workflow decides the next state → Domain service."*
The workflow, not the tool dispatcher, remains the sole place a state transition happens —
otherwise `CallSessionWorkflow`'s `_resolution`/`_state` bookkeeping (and therefore
`resolve_disposition`) silently goes stale the moment a tool call bypasses it.

So `dispatch_tool_call` splits into two shapes, decided per tool:

**(a) Pure reads — answered directly, no signal.** `get_claim_status`,
`explain_next_step`, `list_missing_documents`, `get_authoritative_eta`,
`get_insurer_identity`. These call a (new, read-only) `claims/service.py` function and
return its result straight to the LLM within the same turn — there is no state to change.

**(b) Everything else — bridged onto a `CustomerIntentSignal` and signalled into the running
workflow**, which executes the matching activity exactly as it already does for
customer-utterance-sourced intents. `voice/pipeline.py` is the only thing that both calls
`dispatch_tool_call` (for shape (a)) and signals the workflow (for shape (b)) — the LLM
itself never touches a Temporal client.

| Tool (`voice/tools.py`) | Shape | Resolution |
|---|---|---|
| `get_insurer_identity` | (a) read | static string constant, no DB |
| `get_claim_status` | (a) read | `claims/service.py::get_disclosable_status` — **`verification_level` arg is ignored**; the real value comes from `CallSessionWorkflow.current_verification_level()` (§0.1) |
| `explain_next_step` | (a) read | new `claims/service.py::get_next_step_message_key()` |
| `list_missing_documents` | (a) read | new `claims/service.py::list_missing_documents()` |
| `get_authoritative_eta` | (a) read | new `claims/service.py::get_authoritative_eta()` |
| `request_verification` | (b) signal | `customer_utterance(intent="REQUEST_OTP")` — the existing branch in `_run_authentication` (`phase-1-backend-spec.md` §3.2) already handles this; the tool is the LLM's way of *deciding* a step-up is needed, the workflow still owns whether it's honored |
| `schedule_callback` | (b) signal | new intent `"AI_SCHEDULE_CALLBACK"` (see §4.2) — generalizes the existing `CUSTOMER_DRIVING` callback branch to any AI-initiated callback, not only the driving case |
| `register_inquiry` | (b) signal | new intent `"ASK_QUESTION"` variant — reuses the existing `ASK_QUESTION` branch; `register_inquiry`'s `category`/`summary` populate `CustomerIntentSignal.topic`/`summary` |
| `create_action` | (b) signal | new intent `"AI_CREATE_ACTION"` (see §4.2) — generalizes the existing `DISPUTE_DOCUMENT`/`DISSATISFIED` action-creation branches to an LLM-classified action code |
| `create_escalation` | (b) signal | `human_request_detected()` — already exists, already routes through `_escalate_to_human` |
| `register_complaint` | (b) signal | `customer_utterance(intent="COMPLAINT_REQUEST")` — already exists |
| `send_secure_link` | (b) signal | new intent `"AI_SEND_SECURE_LINK"` — new activity, §4.3 |
| `warm_transfer` | (b) signal | `human_request_detected()` — same as `create_escalation`; `reason` populates the escalation's context snapshot |

This table is the actual deliverable of "wire the tools to real services" — it is what a
reviewer checks a PR against, not a vague "implement the stubs" instruction.

**Why the LLM's `verification_level` argument is untrusted (spec §36 rule 1):**
`GetClaimStatusArgs.verification_level` exists in the schema only so the LLM's tool call is
well-typed and the model can reason about it in its own chain of thought — the dispatcher
never reads that field to decide what to disclose. It always re-fetches the authoritative
value via the workflow query before calling `get_disclosable_status`. A test
(`tests/unit/test_tool_dispatch_verification_authority.py`) asserts that a tool-call
`args` dict with a forged `"verification_level": "L2"` on an actually-`L0` session still
returns the redacted (`L0`) response — this is the mechanical enforcement of the single
most important rule in `CLAUDE.md`.

### 0.4 DTMF fallback and adversarial-input tagging are **generalized interrupt signals**, not new `CallState`s

`CallSessionWorkflow` already has exactly one signal that behaves this way:
`call_dropped()` — it sets a flag (`self._call_dropped`) that every `_wait_for_signal`-based
stage checks immediately, regardless of which stage is currently waiting (per
`phase-1-backend-spec.md` §3.2's "any `_wait_for_signal` call that returns because
`call_dropped()` fired ... routes to `_finalize`"). DTMF fallback needs the identical shape:
spec §8.9's trigger (`MAX_CONSECUTIVE_LOW_STT_TURNS = 3`) can fire during right-party check,
authentication, or follow-up — it is a cross-cutting interrupt, exactly like a dropped call,
not a state confined to one stage.

`CallSessionWorkflow` gains one new signal:

```python
@workflow.signal
async def dtmf_fallback(self, action: Literal["CALLBACK", "HUMAN"]) -> None:
    self._dtmf_fallback_action = action
```

`_wait_for_signal`'s `wait_condition` predicate extends to
`bool(self._pending_signals) or self._call_dropped or self._dtmf_fallback_action is not None`,
and every stage's "signal is None" branch gains a DTMF check ahead of the existing
`call_dropped` check (DTMF fires deterministically off `pipeline.py`'s own counter — it is
never itself the LLM's decision, so there is nothing to arbitrate; the workflow just routes):

```python
if self._dtmf_fallback_action == "CALLBACK":
    await workflow.execute_activity(calls_activities.schedule_callback, ...)
    return await self._finalize(inp, attempt_id, final_state=CallState.CLOSE,
                                 dtmf_fallback=True, callback_requested=True)
if self._dtmf_fallback_action == "HUMAN":
    return await self._escalate_to_human(inp, attempt_id, reason="DTMF_FALLBACK")
```

`DispositionContext` (`calls/disposition.py`) gains one new boolean, `dtmf_fallback: bool =
False`, checked in `resolve_disposition` ahead of the `match ctx.final_state` block (same
priority tier as `call_dropped`/`otp_locked`/`backend_unavailable` — "why the call ended,"
not "what state it ended in"), resolving to the already-existing
`DispositionCode.DTMF_FALLBACK_ACTIVATED`. No enum values are added anywhere — Phase 0/1
already named every code this phase needs (`DTMF_FALLBACK_ACTIVATED`,
`ADVERSARIAL_INPUT_DETECTED`, `SECURITY_POLICY_ESCALATION` are all already in
`calls/constants.py::DispositionCode`).

Adversarial-input tagging (spec §2.2.2 rule 4) follows the **audit-only** half of this same
shape but deliberately does **not** get its own workflow signal this phase: `voice/guard.py`
classifies a caller utterance as adversarial, `pipeline.py` calls
`calls_activities.record_audit_event` directly (the same Phase 0 activity every other
transition already uses) with `reason_code="ADVERSARIAL_INPUT_DETECTED"` — this satisfies
spec §36 rule 10 ("all calls and decisions must produce structured audit events") and rule 5
("detection must not by itself accuse the customer of wrongdoing; continue using the normal
workflow boundary") without inventing a state transition for it. If adversarial input
*persists* (a same-call counter in `pipeline.py`, not workflow state — see §6), `pipeline.py`
calls the existing `human_request_detected()` signal with reason
`"SECURITY_POLICY_ESCALATION"` in the escalation's context snapshot — reusing
`_escalate_to_human`, not adding a new escalation path. `ADVERSARIAL_INPUT_DETECTED` and
`CUSTOMER_VULNERABILITY_INDICATED`/`FRAUD_SUSPECTED`/etc. remain in
`FUTURE_GLOBAL_INTERRUPTS` for anything beyond this narrow slice — full fraud/vulnerability/
legal-sensitivity routing is Phase 5's `risk/` package, which does not exist yet and this
phase does not create.

### 0.5 `voice/guard.py`'s job is narrow on purpose

Per §0.4 and per the phase file's own Notes ("the free-tier/self-hosted vendors ... are not
the vendors whose adversarial-resistance gets hardened in Phase 4/5"), `guard.py` this phase
is a cheap keyword/pattern classifier (spec §2.2.2's example phrase list — "system override,"
"ignore your instructions," "developer mode," etc. — plus a small confidence-scored intent
classifier if the chosen free-tier LLM supports a fast classification call). It is explicitly
**not** the hardened adversarial-resistance work Phase 4/5 re-runs against Claude. Its
contract is one pure function:

```python
# src/voice/guard.py
def classify_adversarial(utterance: str) -> AdversarialClassification:
    """Returns {is_adversarial: bool, matched_pattern: str | None, confidence: float}.
    Never raises, never calls a workflow, never touches call state — a signal source only,
    per spec §2.2.2 rule 5."""
```

`voice/prompt.py`'s existing structural guarantee (no `str` parameter for raw text) already
prevents this classifier's *input* from becoming prompt-injected system-prompt content —
`guard.py` reads the same already-transcribed utterance `pipeline.py` also feeds to intent
extraction, it does not get special raw access to anything the rest of the pipeline doesn't.

### 0.6 Latency telemetry reuses `BACKEND_SOFT_WAIT_MS`; it does not invent a second threshold

`src/config.py` already carries `BACKEND_SOFT_WAIT_MS: int = 1500` with a docstring pointing
at spec §2.2.1 and naming `calls/activities.py::with_runtime_recovery` as its Phase 1
consumer — this phase's holding-phrase logic in `voice/pipeline.py` is the *second* consumer
of the exact same setting, not a new `HOLDING_PHRASE_THRESHOLD_MS`. `voice/config.py` adds
only what's genuinely voice-pipeline-specific and not already global:

```python
class VoiceConfig(BaseSettings):
    TARGET_TURN_P95_MS: int = 1500        # spec §2.2.1
    MODEL_TIMEOUT_MS: int = 5000
    MAX_HOLDING_PHRASES_PER_OPERATION: int = 1
    MAX_CONSECUTIVE_LOW_STT_TURNS: int = 3   # spec §8.9
```

OpenTelemetry spans wrap each hop (`STT`, `LLM_ORCHESTRATION`, `BACKEND_TOOL`,
`TTS_FIRST_BYTE`, `TOTAL_TURN`) inside `voice/pipeline.py`'s turn loop — this is
instrumentation around the existing turn loop, not a parallel measurement system, so P50/P95/
P99 come out of the same span data Phase 3's dashboard will later read (`LatencyMetricsPanel`,
per `CLAUDE.md` §3.3), not a bespoke metrics table this phase invents and Phase 3 has to
migrate away from.

### 0.7 Language is call-session state, not a new domain

Spec §2.2.3 requires storing "detected language per turn for QA." `CallSession`
(`calls/models.py`) gains one column, `language: Mapped[str] = mapped_column(default="en")`
— the *current* language for the session, updated by `pipeline.py` via the existing
`update_call_session` activity/`UpdateCallSessionInput` schema (extended with an optional
`language` field) every time the STT layer's detected language for a turn differs from the
stored value. Full per-turn history (every turn's detected language, not just "current") is
part of `CallTranscript`/`CallEvent`, which are Phase 3 tables per
`phase-1-backend-spec.md` §17 — this phase stores only what `PromptContext.language`
(already exists) needs to stay correct turn-to-transducer-to-turn, and what a same-call
DTMF/QA reviewer needs from `CallSession` directly. `PromptContext.language` is populated
from this column, never inferred fresh by `pipeline.py` bypassing the stored value.

Building and testing English, then Arabic, then mixed/code-switching **sequentially** (per
the phase file's explicit instruction) is a rollout/test-ordering decision, not a code fork —
there is exactly one `voice/pipeline.py`, one `PromptContext.language` field carrying
`"en" | "ar" | "mixed"`, and the STT adapter's language-detection output flows into it
regardless of which language is currently being demoed. Do not build an `if language ==
"ar":` branch anywhere in `pipeline.py` itself — language-specific behavior belongs in the
STT/TTS adapter's config (voice model selection) and in the prompt template
`build_system_prompt` selects by `context.language`, nowhere else.

### 0.8 Answer detection stays the Phase 1 stub this phase; no change to `classify_answer`

The browser-WebRTC demo transport has no PSTN ring/silence/voicemail signal to classify —
`CallSessionInput.simulated_answer_result` (already `"HUMAN_ANSWERED"` by default) stays
exactly as Phase 1 built it. A real telephony vendor's answer-detection integration
(spec §5) is explicitly a Phase 6 production-vendor-swap concern, per
`phase-1-backend-spec.md`'s own deferral note — this phase's `telephony/browser_webrtc.py`
adapter is a **conversation transport**, not an answer-detection source, and must not be
built as if it were.

---

## 1. Domain package layout — the Phase 1 → Phase 2 diff

Everything in `backend/src/` from Phase 1 stays untouched except the two explicit additions
called out below (`calls/`'s new signal/query/disposition flag, `calls/models.py`'s new
column). Unmarked files are new; `(+)` marks a Phase-1 file gaining new content.

```
backend/
├── src/
│   ├── calls/
│   │   ├── constants.py        (+) no new enum values — DTMF_FALLBACK_ACTIVATED,
│   │   │                            ADVERSARIAL_INPUT_DETECTED, SECURITY_POLICY_ESCALATION
│   │   │                            already exist from Phase 0
│   │   ├── schemas.py          (+) IntentName gains "AI_SCHEDULE_CALLBACK",
│   │   │                            "AI_CREATE_ACTION", "AI_SEND_SECURE_LINK" (§4.2);
│   │   │                            UpdateCallSessionInput gains optional `language`
│   │   ├── models.py           (+) CallSession.language column (§0.7)
│   │   ├── disposition.py      (+) DispositionContext.dtmf_fallback: bool, one new
│   │   │                            resolve_disposition branch (§0.4)
│   │   ├── activities.py       (+) send_secure_link activity (§4.3); no other activity
│   │   │                            changes — every activity Phase 2 needs already exists
│   │   └── workflows.py        (+) dtmf_fallback() signal, current_verification_level()
│   │                                and current_claim_context() queries (§0.1/§0.4)
│   ├── claims/
│   │   └── service.py          (+) get_next_step_message_key(), list_missing_documents(),
│   │                                get_authoritative_eta() — read-only, no schema changes
│   ├── voice/
│   │   ├── tools.py            (+) dispatch_tool_call's 13 NotImplementedError bodies
│   │   │                            replaced per the §0.3 table; module otherwise unchanged
│   │   ├── prompt.py           (+) build_system_prompt's NotImplementedError replaced with
│   │   │                            the real English/Arabic template selection (§5)
│   │   ├── config.py            # NEW — VoiceConfig(BaseSettings), §2
│   │   ├── pipeline.py          # NEW — Pipecat pipeline assembly, the turn loop, §5
│   │   ├── guard.py             # NEW — adversarial-input classifier, §6
│   │   ├── dtmf.py               # NEW — consecutive-low-confidence counter + fallback
│   │   │                            prompt text, §7
│   │   ├── telemetry.py          # NEW — OpenTelemetry span helpers for the turn loop, §8
│   │   └── adapters/
│   │       ├── stt/
│   │       │   ├── base.py       # NEW — SpeechToTextAdapter Protocol
│   │       │   ├── whisper.py    # NEW — faster-whisper, self-hosted
│   │       │   └── groq_whisper.py # NEW — Groq free-tier hosted Whisper API
│   │       ├── tts/
│   │       │   ├── base.py       # NEW — TextToSpeechAdapter Protocol
│   │       │   └── piper.py      # NEW — Piper TTS, self-hosted, English + community Arabic voice
│   │       ├── llm/
│   │       │   ├── base.py       # NEW — ConversationLlmAdapter Protocol
│   │       │   ├── gemini.py     # NEW — Gemini API free tier
│   │       │   └── groq_llm.py   # NEW — Groq free tier (Llama 3.3 70B / Qwen2.5)
│   │       └── telephony/
│   │           ├── base.py       # NEW — TelephonyTransportAdapter Protocol
│   │           └── browser_webrtc.py  # NEW — Pipecat SmallWebRTCTransport wrapper
│   └── temporal_client.py       (+) exports get_client() shared by worker.py AND
│                                     voice_server.py (currently only worker.py uses it
│                                     directly — check for duplication before adding)
├── voice_server.py               # NEW — the Pipecat real-time server process, §11
├── requirements/
│   └── base.txt                 (+) pipecat-ai, opentelemetry-sdk,
│                                     opentelemetry-exporter-otlp, faster-whisper OR groq
│                                     (whichever adapter ships first — §14), piper-tts
├── scripts/ci/
│   ├── check_tool_allowlist.py  (+) no code change — now exercises real call sites in
│                                     pipeline.py for the first time (§15)
│   └── check_no_raw_prompt_concat.py (+) no code change — now exercises pipeline.py/
│                                     guard.py for the first time (§15)
└── tests/
    ├── unit/
    │   ├── test_tool_dispatch_verification_authority.py  # NEW — §0.3
    │   ├── test_dtmf_fallback_counter.py                  # NEW — §7
    │   ├── test_guard_classifier.py                       # NEW — §6
    │   └── test_disposition_resolution.py                (+) new DTMF_FALLBACK_ACTIVATED case
    └── integration/
        ├── test_phase2_pipeline_signal_bridge.py          # NEW — §12
        └── test_phase2_demo1_demo4_e2e.py                 # NEW — §12/§17
```

---

## 2. `voice/config.py` — `VoiceConfig(BaseSettings)`

Following `CLAUDE.md` §2.7/§2.8 exactly — a domain-specific `BaseSettings` subclass, not an
addition to the global `Config`:

```python
# src/voice/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class VoiceConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    STT_PROVIDER: str = "whisper"          # "whisper" | "groq_whisper"
    TTS_PROVIDER: str = "piper"            # "piper" (only demo-tier option this phase)
    LLM_PROVIDER: str = "gemini"           # "gemini" | "groq_llm"
    TELEPHONY_PROVIDER: str = "browser"    # "browser" (only demo-tier option this phase)

    GROQ_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None

    TARGET_TURN_P95_MS: int = 1500
    MODEL_TIMEOUT_MS: int = 5000
    MAX_HOLDING_PHRASES_PER_OPERATION: int = 1
    MAX_CONSECUTIVE_LOW_STT_TURNS: int = 3
    STT_LOW_CONFIDENCE_THRESHOLD: float = 0.55


voice_settings = VoiceConfig()  # type: ignore[call-arg]
```

Provider selection is a small factory per adapter family, called once at `voice_server.py`
startup — never inside the per-turn hot path:

```python
# src/voice/adapters/stt/__init__.py
def get_stt_adapter() -> "SpeechToTextAdapter":
    if voice_settings.STT_PROVIDER == "groq_whisper":
        from src.voice.adapters.stt.groq_whisper import GroqWhisperAdapter
        return GroqWhisperAdapter(api_key=voice_settings.GROQ_API_KEY)
    from src.voice.adapters.stt.whisper import FasterWhisperAdapter
    return FasterWhisperAdapter()
```

Same shape repeats for `tts`/`llm`/`telephony`. `voice/pipeline.py` imports only these
factory functions, never a provider module by name.

---

## 3. Adapter protocols (tasks: STT/LLM/TTS/telephony as swappable adapters)

Each `base.py` is a `Protocol`, per `CLAUDE.md` §2.7's example verbatim:

```python
# src/voice/adapters/stt/base.py
from typing import AsyncIterator, Protocol


class Transcript(BaseModel):
    text: str
    language: str            # "en" | "ar" | "mixed" — spec §2.2.3
    confidence: float
    is_final: bool


class SpeechToTextAdapter(Protocol):
    async def stream(self, audio: AsyncIterator[bytes]) -> AsyncIterator[Transcript]: ...
```

```python
# src/voice/adapters/tts/base.py
class TextToSpeechAdapter(Protocol):
    async def synthesize(self, text: str, *, language: str) -> AsyncIterator[bytes]:
        """Streamed/chunked audio bytes — spec §2.2.1's 'use streaming/chunked TTS so
        speech can begin before the full response is generated.'"""
        ...
```

```python
# src/voice/adapters/llm/base.py
class LlmTurnResult(BaseModel):
    kind: Literal["text", "tool_call"]
    text: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None


class ConversationLlmAdapter(Protocol):
    async def complete(
        self, *, system_prompt: str, utterance: str, tools: list[ToolSpec]
    ) -> LlmTurnResult: ...
```

`ConversationLlmAdapter.complete`'s signature is deliberately narrow — `system_prompt` (built
once per turn by `build_system_prompt`, never raw text) and `utterance` (the caller's latest
transcribed turn, and nothing else — no conversation history concatenation of raw prior
turns; multi-turn context that matters is already baked into `PromptContext` by the workflow,
per spec §36 rule 4). This is the structural continuation of `voice/prompt.py`'s existing
"no `str` parameter for arbitrary text" discipline, extended to the adapter boundary.

```python
# src/voice/adapters/telephony/base.py
class TelephonyTransportAdapter(Protocol):
    def build_transport(self, *, session_id: str) -> "PipecatTransport":
        """Returns a Pipecat-native transport instance — this Protocol wraps transport
        *construction*, not per-call I/O, since Pipecat's own transport classes already
        define the runtime interface."""
        ...
```

`telephony/browser_webrtc.py` wraps Pipecat's `SmallWebRTCTransport` (or equivalent
WebRTC-over-aiohttp transport Pipecat ships) — this is the one adapter whose implementation
is mostly "construct the vendor/library object with our config," since Pipecat already
provides the WebRTC transport; there is no custom protocol implementation to write.

`stt/whisper.py` (faster-whisper, self-hosted) and `stt/groq_whisper.py` (Groq's hosted
Whisper API) both implement `SpeechToTextAdapter.stream`; `tts/piper.py` implements
`TextToSpeechAdapter.synthesize`, evaluated against a community Arabic Piper/Coqui voice per
`IMPLEMENTATION_PLAN.md`'s explicit note that demo Arabic TTS quality is a placeholder;
`llm/gemini.py` and `llm/groq_llm.py` both implement `ConversationLlmAdapter.complete` using
each vendor's function-calling API, translating `ToolSpec.args_schema` into that vendor's
tool/function-declaration format at the adapter boundary — `TOOL_REGISTRY` itself stays
vendor-agnostic.

---

## 4. The tool-dispatch → signal bridge (implementing §0.3's table)

### 4.1 New workflow queries — `current_verification_level`, `current_claim_context`

```python
# src/calls/workflows.py additions
@workflow.query
def current_verification_level(self) -> str:
    return self._verification_level or "L0"

@workflow.query
def current_claim_context(self) -> dict:
    return {"claim_id": self._claim_id, "customer_first_name": self._customer_first_name}
```

(`self._claim_id`/`self._customer_first_name` are stored in `__init__`/`run` from
`CallSessionInput` — trivial additions alongside the existing `self._right_party` etc.
bookkeeping fields.) `voice/pipeline.py` calls these via the Temporal client
(`handle.query(CallSessionWorkflow.current_verification_level)`) once per turn, immediately
before calling `dispatch_tool_call`, and threads the result into `PromptContext` and into any
read-shape tool call — never accepting the LLM's own claimed value.

### 4.2 `IntentName` extensions

```python
# src/calls/schemas.py — IntentName gains three AI-initiated variants
IntentName = Literal[
    # ... all 13 existing values, unchanged ...
    "AI_SCHEDULE_CALLBACK",   # from the schedule_callback tool
    "AI_CREATE_ACTION",       # from the create_action tool
    "AI_SEND_SECURE_LINK",    # from the send_secure_link tool
]
```

`CustomerIntentSignal` needs no new fields — `topic`/`summary`/`document_type` already cover
what these three carry (action code goes in `topic`, the free-text goes in `summary`).

### 4.3 New activity — `send_secure_link`

The only genuinely new activity this phase adds (every other bridged tool reuses an existing
Phase 1 activity):

```python
# src/calls/activities.py addition
class SendSecureLinkInput(BaseModel):
    key: str
    correlation_id: str
    customer_id: str
    link_type: str

@activity.defn
async def send_secure_link(inp: SendSecureLinkInput) -> dict[str, Any]:
    async with SessionLocal() as session:
        return await idempotent(
            session, key=inp.key, correlation_id=inp.correlation_id,
            operation_name="send_secure_link",
            payload=inp.model_dump(),
            operation=lambda: _send_secure_link(session, inp),
        )
```

Same idempotent-write shape every other Phase 1 write activity already uses (per
`phase-1-backend-spec.md` §8.1) — no new pattern introduced. Added to `ALL_CALLS_ACTIVITIES`
in the same module; `worker.py` needs **no change** since it already imports
`ALL_CALLS_ACTIVITIES` as a list, not by naming individual functions.

### 4.4 `voice/tools.py`'s real `dispatch_tool_call` body

```python
async def dispatch_tool_call(
    *, name: str, args: dict[str, Any], call_id: str, workflow_handle: WorkflowHandle
) -> dict[str, Any]:
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        raise UnknownToolError(name)
    validated = spec.args_schema.model_validate(args)

    if name in _READ_TOOLS:
        return await _READ_TOOLS[name](validated, workflow_handle)

    intent = _WRITE_TOOL_INTENTS[name](validated)  # builds a CustomerIntentSignal
    await workflow_handle.signal(CallSessionWorkflow.customer_utterance, intent)
    return {"status": "signalled"}
```

`workflow_handle` is a new required parameter — Phase 0's stub had none because nothing
called it yet. `_READ_TOOLS`/`_WRITE_TOOL_INTENTS` are two small dicts built from §0.3's
table, each entry a short function, not a large `if/elif` chain — keeps the table in the spec
and the table in the code in 1:1 correspondence, so a reviewer can diff them.

---

## 5. `voice/pipeline.py` — the Pipecat pipeline assembly

The turn loop, per the phase file's task list and spec §2.2's diagram:

```python
# src/voice/pipeline.py (turn-loop sketch — Pipecat's own Pipeline/FrameProcessor
# machinery wraps this; the sequence below is the logical shape regardless of exactly
# which Pipecat primitives wire it)

async def handle_turn(ctx: CallPipelineContext, audio_frames: AsyncIterator[bytes]) -> None:
    with telemetry.span("STT"):
        transcript = await ctx.stt.stream(audio_frames)  # -> Transcript(text, language, confidence)

    if transcript.confidence < voice_settings.STT_LOW_CONFIDENCE_THRESHOLD:
        if dtmf.register_low_confidence_turn(ctx.call_id) >= voice_settings.MAX_CONSECUTIVE_LOW_STT_TURNS:
            await dtmf.activate_fallback(ctx)   # §7 — deterministic TTS prompt, no LLM
            return
    else:
        dtmf.reset_counter(ctx.call_id)

    guard_result = guard.classify_adversarial(transcript.text)
    if guard_result.is_adversarial:
        await calls_activities.record_audit_event(RecordAuditEventInput(
            decision="ADVERSARIAL_INPUT_TAGGED", reason_code="ADVERSARIAL_INPUT_DETECTED",
            call_id=ctx.attempt_id, correlation_id=ctx.call_id, actor="AI",
        ))
        if ctx.adversarial_streak.increment() >= voice_settings.MAX_ADVERSARIAL_STREAK:
            await ctx.workflow_handle.signal(CallSessionWorkflow.human_request_detected)
            return

    verification_level = await ctx.workflow_handle.query(CallSessionWorkflow.current_verification_level)
    claim_ctx = await ctx.workflow_handle.query(CallSessionWorkflow.current_claim_context)

    prompt_context = PromptContext(
        claim_stage=claim_ctx["claim_stage"], verification_level=verification_level,
        language=transcript.language, customer_first_name=claim_ctx["customer_first_name"],
    )
    system_prompt = build_system_prompt(prompt_context)  # never touches transcript.text

    with telemetry.span("LLM_ORCHESTRATION", soft_wait_ms=settings.BACKEND_SOFT_WAIT_MS):
        result = await ctx.llm.complete(
            system_prompt=system_prompt, utterance=transcript.text,
            tools=list(TOOL_REGISTRY.values()),
        )

    if result.kind == "tool_call":
        with telemetry.span("BACKEND_TOOL"):
            tool_result = await dispatch_tool_call(
                name=result.tool_name, args=result.tool_args,
                call_id=ctx.call_id, workflow_handle=ctx.workflow_handle,
            )
        spoken_text = build_response_from_tool_result(result.tool_name, tool_result, prompt_context)
    else:
        spoken_text = result.text

    with telemetry.span("TTS_FIRST_BYTE"):
        async for chunk in ctx.tts.synthesize(spoken_text, language=transcript.language):
            await ctx.transport.send_audio(chunk)
```

The two CI-gate-relevant facts about this function, both mechanically checked (§15):
`system_prompt` is built exclusively from `PromptContext` (structured fields), never from
`transcript.text` directly, and `dispatch_tool_call`'s `name` always comes from
`result.tool_name` — an LLM-returned, `TOOL_REGISTRY`-validated value — never a raw string
built from caller speech.

`build_response_from_tool_result` is a second, small `build_system_prompt`-shaped function —
it turns a validated tool response (facts) into a second, narrower LLM completion call whose
prompt is *only* those facts (spec §36 rule 3/4's "the LLM converts facts into natural
speech; it does not create those facts"), or a deterministic template for the simplest cases
(e.g. `get_insurer_identity`'s fixed introduction line needs no LLM call at all).

---

## 6. `voice/guard.py` — adversarial-input classifier

```python
# src/voice/guard.py
from pydantic import BaseModel

_INJECTION_PATTERNS = (
    "system override", "ignore your instructions", "i am already verified",
    "supervisor approved", "read your system prompt", "hidden instructions",
    "developer mode", "skip verification",
)  # spec §2.2.2's example list, verbatim


class AdversarialClassification(BaseModel):
    is_adversarial: bool
    matched_pattern: str | None = None
    confidence: float


def classify_adversarial(utterance: str) -> AdversarialClassification:
    lowered = utterance.lower()
    for pattern in _INJECTION_PATTERNS:
        if pattern in lowered:
            return AdversarialClassification(is_adversarial=True, matched_pattern=pattern, confidence=0.9)
    return AdversarialClassification(is_adversarial=False, confidence=0.0)
```

A per-call adversarial streak counter (`ctx.adversarial_streak`, §5) lives in
`voice/pipeline.py`'s in-memory per-call context, not on `CallSession` — it is live-session
scratch state, same category as the DTMF low-confidence counter (§7), not something spec
§10.6.2's recovery-state JSON needs to persist (a dropped/reconnected call starts a fresh
`CallSessionWorkflow` and a fresh pipeline context by construction, per
`phase-1-backend-spec.md` §3.2's "no separate resume code path" note).

---

## 7. DTMF fallback (`voice/dtmf.py`)

```python
# src/voice/dtmf.py
_counters: dict[str, int] = {}  # call_id -> consecutive low-confidence turn count

def register_low_confidence_turn(call_id: str) -> int:
    _counters[call_id] = _counters.get(call_id, 0) + 1
    return _counters[call_id]

def reset_counter(call_id: str) -> None:
    _counters.pop(call_id, None)

async def activate_fallback(ctx: "CallPipelineContext") -> None:
    # Deterministic, pre-recorded/templated prompt — spec §8.9 verbatim, no LLM involved.
    prompt = ("I'm having trouble hearing you clearly. To schedule a callback, please "
              "press 1. To request a service agent, please press 2.")
    async for chunk in ctx.tts.synthesize(prompt, language=ctx.language):
        await ctx.transport.send_audio(chunk)
    digit = await ctx.transport.receive_dtmf(timeout_seconds=15)
    if digit == "1":
        await ctx.workflow_handle.signal(CallSessionWorkflow.dtmf_fallback, "CALLBACK")
    elif digit == "2":
        await ctx.workflow_handle.signal(CallSessionWorkflow.dtmf_fallback, "HUMAN")
    else:
        # NO INPUT / INVALID INPUT — repeat once, then safe close or human callback
        # per spec §8.9's minimum mapping; a second failure routes to HUMAN.
        await ctx.workflow_handle.signal(CallSessionWorkflow.dtmf_fallback, "HUMAN")
```

The in-memory `_counters` dict keyed by `call_id` is process-local scratch state, same
reasoning as §6's adversarial streak — it does not need to survive a process restart because
a restart mid-call is already a dropped-call case per spec §10.6.3, handled by the existing
`call_dropped` path, not by DTMF-counter recovery.

`ctx.transport.receive_dtmf` is a small addition to `TelephonyTransportAdapter`'s concrete
`browser_webrtc.py` implementation (Pipecat's WebRTC transport surfaces DTMF via RFC 4733/
in-band tones or a data-channel message depending on the browser client's implementation;
the demo's browser client sends DTMF as a data-channel message, since real telephone keypad
tones don't exist in a browser-mic demo — this is documented as a demo-transport limitation,
not hidden as if it were the production behavior).

---

## 8. Latency telemetry (`voice/telemetry.py`)

```python
# src/voice/telemetry.py
from contextlib import asynccontextmanager
from opentelemetry import trace

_tracer = trace.get_tracer("voice.pipeline")

@asynccontextmanager
async def span(name: str, **attributes):
    with _tracer.start_as_current_span(name, attributes=attributes) as s:
        yield s
```

Five spans per turn, matching spec §2.2.1's chain exactly: `STT`, `LLM_ORCHESTRATION`,
`BACKEND_TOOL`, `TTS_FIRST_BYTE`, and an outer `TOTAL_TURN` span `handle_turn` itself is
wrapped in (not shown in §5's sketch for brevity — it wraps the whole function body).
Exporting to Prometheus/Grafana (per `IMPLEMENTATION_PLAN.md`'s demo-tier stack) is an
OpenTelemetry OTLP exporter configured once in `voice_server.py`'s startup, not per-span
code — `voice/telemetry.py` itself stays exporter-agnostic.

The holding-phrase mechanism: if `BACKEND_TOOL`'s span exceeds `BACKEND_SOFT_WAIT_MS` before
`dispatch_tool_call` returns, `pipeline.py` plays exactly one (per
`MAX_HOLDING_PHRASES_PER_OPERATION`) deterministic phrase — "Just a moment while I retrieve
that information" (spec §2.2.1's literal example) — via `ctx.tts.synthesize`, never an
LLM-generated filler. This is implemented as a `asyncio.wait_for`/timeout race around the
`dispatch_tool_call` await, not a callback the LLM can influence:

```python
try:
    tool_result = await asyncio.wait_for(
        dispatch_tool_call(...), timeout=voice_settings.MODEL_TIMEOUT_MS / 1000
    )
except asyncio.TimeoutError:
    # exceeded BACKEND_SOFT_WAIT_MS already triggered the holding phrase via a separate,
    # shorter concurrent timer — see the soft-wait vs. hard-timeout distinction below.
```

Two distinct timers, not one: `BACKEND_SOFT_WAIT_MS` (1500ms) triggers the holding phrase
while the tool call is still in flight (spec §2.2.1's "if genuinely pending beyond the
configured threshold, play a holding phrase"); `MODEL_TIMEOUT_MS` (5000ms) is the hard
timeout that, if exceeded, routes to spec §10.6.1's Runtime Failure framework (`LLM_TIMEOUT`/
`BACKEND_TIMEOUT` disposition family — already-existing `DispositionCode` values) via the
same `_finalize(..., backend_unavailable=True)` path `_run_status_and_follow_up` already uses
for a failed `deliver_status` call. No new failure-handling code path — this phase's timeout
just triggers the one that already exists.

---

## 9. Language & code-switching

Covered structurally in §0.7. The one piece of net-new logic: `voice/pipeline.py` calls
`update_call_session` (existing activity, extended `UpdateCallSessionInput.language`
parameter) whenever `transcript.language != ctx.current_language`, so `CallSession.language`
always reflects the most recent turn's detected language — this is what `PromptContext`
reads on the *next* turn, and what an explicit "Arabic please"/"English please" override
(spec §2.2.3) writes directly, bypassing the STT detector for that one turn:

```python
if "arabic please" in transcript.text.lower():
    ctx.current_language = "ar"
elif "english please" in transcript.text.lower():
    ctx.current_language = "en"
else:
    ctx.current_language = transcript.language if transcript.confidence >= _LANGUAGE_CONFIDENCE_FLOOR else ctx.current_language
```

("Ask a simple language preference question rather than guessing" when confidence is low is
a `build_response_from_tool_result`-style deterministic template, not a new state.)

---

## 10. `calls/` additions summary

Already detailed in §0.1/§0.4/§0.7/§4.1/§4.2/§4.3 — consolidated here for the migration:

- `calls/workflows.py`: `dtmf_fallback()` signal, `current_verification_level()` and
  `current_claim_context()` queries, `self._dtmf_fallback_action` field, one new branch per
  `_wait_for_signal`-based stage (§0.4).
- `calls/disposition.py`: `DispositionContext.dtmf_fallback: bool = False`, one new
  `resolve_disposition` branch resolving to the existing `DispositionCode.DTMF_FALLBACK_ACTIVATED`.
- `calls/schemas.py`: `IntentName` +3 values (§4.2); `UpdateCallSessionInput` +1 optional
  field (`language: str | None = None`).
- `calls/models.py`: `CallSession.language: Mapped[str] = mapped_column(default="en")`.
- `calls/activities.py`: `send_secure_link` activity + its `SendSecureLinkInput` schema,
  added to `ALL_CALLS_ACTIVITIES`.

---

## 11. `voice_server.py` — the real-time server process

```python
# backend/voice_server.py
import asyncio
from aiohttp import web

from src.temporal_client import get_client
from src.voice.adapters.stt import get_stt_adapter
from src.voice.adapters.tts import get_tts_adapter
from src.voice.adapters.llm import get_llm_adapter
from src.voice.adapters.telephony.browser_webrtc import BrowserWebRtcAdapter
from src.voice.pipeline import run_call_pipeline


async def offer_handler(request: web.Request) -> web.Response:
    """WebRTC SDP offer/answer exchange for the browser-demo transport — Pipecat's
    SmallWebRTCTransport ships an aiohttp handler shape this wraps; the browser client
    (a small demo page, not part of frontend/ — see decision below) POSTs its SDP offer
    here and gets an answer back, then media flows peer-to-peer/over the negotiated
    connection, not through further HTTP calls."""
    body = await request.json()
    transport = BrowserWebRtcAdapter().build_transport(session_id=body["call_id"])
    answer = await transport.handle_offer(body["sdp"])
    client = await get_client()
    asyncio.create_task(run_call_pipeline(
        call_id=body["call_id"], transport=transport, client=client,
        stt=get_stt_adapter(), tts=get_tts_adapter(), llm=get_llm_adapter(),
    ))
    return web.json_response({"sdp": answer})


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/offer", offer_handler)
    app.router.add_get("/health", lambda _: web.json_response({"status": "ok"}))
    return app


if __name__ == "__main__":
    web.run_app(build_app(), port=8765)
```

**Why `aiohttp`, not another FastAPI app**: Pipecat's WebRTC transport helpers are built
against `aiohttp` upstream; wrapping them in a second FastAPI instance would add an
indirection layer for no benefit, and `CLAUDE.md` already treats `voice_server.py` as its own
independent process/deployable — it was never expected to share `main.py`'s app instance.
`src/temporal_client.py::get_client()` is a small addition (a cached `Client.connect(...)`
coroutine) shared between `worker.py` and `voice_server.py`, avoiding two independent
connection-setup implementations.

**Where the browser demo page itself lives**: a minimal static HTML/JS page (mic capture +
WebRTC negotiation against `/offer`) is a demo harness, not a dashboard feature — it does not
belong under `frontend/` (per `CLAUDE.md`'s "nothing frontend-related belongs under
`backend/`... [dashboard] is an observer... never a participant in a live call" boundary,
which cuts the other way here too: a live-call *participant* UI is not the ops dashboard).
It ships as a static file served by `voice_server.py` itself (`app.router.add_static(...)`)
under e.g. `backend/voice_demo_client/index.html` — new, small, and explicitly out of
`frontend/`'s domain-layered architecture since it has no pages/containers/hooks/services of
its own to speak of.

Docker Compose gains one new service, `voice`, alongside `backend`/`worker` — same build
context, `command: python voice_server.py`, publishing port 8765, depending on `redis`/
`temporal` exactly like `worker` does.

---

## 12. Testing strategy

No real audio in CI — the same discipline Phase 1 applied to no-real-telephony (a
`simulated_answer_result` stub) applies here to no-real-STT/TTS:

- **`tests/unit/test_tool_dispatch_verification_authority.py`**: calls `dispatch_tool_call`
  directly with a mocked `workflow_handle` whose `current_verification_level` query returns
  `"L0"` and asserts a forged `args["verification_level"] = "L2"` still yields the `L0`-
  redacted `get_claim_status` response.
- **`tests/unit/test_dtmf_fallback_counter.py`**: exercises `voice/dtmf.py`'s counter
  directly (no Pipecat, no Temporal) — 3 consecutive low-confidence calls trigger
  `activate_fallback`, a confidence reset in between does not accumulate.
- **`tests/unit/test_guard_classifier.py`**: table-driven over spec §2.2.2's example phrase
  list plus a handful of benign utterances, asserting no false positive on ordinary claim
  questions.
- **`tests/integration/test_phase2_pipeline_signal_bridge.py`**: starts a real
  `CallSessionWorkflow` (Temporal test environment, same pattern
  `test_phase1_e2e.py` already established) and drives it via `dispatch_tool_call`/direct
  signal calls **standing in for** `voice/pipeline.py` — i.e., this test proves the bridge
  table in §0.3 is wired correctly without needing a real STT/LLM/TTS adapter in the loop.
  This is the literal continuation of Phase 1's fake/text harness, now one layer closer to
  the real pipeline (it calls `dispatch_tool_call` instead of raw
  `customer_utterance` signals for every tool-shaped intent).
- **`tests/integration/test_phase2_demo1_demo4_e2e.py`**: the same harness pattern extended
  to run Demo 1 and Demo 4's full branch end-to-end (§17), still without real audio — a
  `FakeSpeechToTextAdapter`/`FakeConversationLlmAdapter`/`FakeTextToSpeechAdapter` trio (test
  doubles implementing the real `Protocol`s) let `voice/pipeline.py`'s actual turn-loop code
  run under test, scripted with a fixed sequence of "utterances" and expected tool calls —
  this is meaningfully stronger than §"signal bridge" test above because it exercises
  `pipeline.py`'s own code, not just the bridge table.
- A **live manual smoke test** (not CI) against the real demo stack — browser mic, real
  Whisper/Piper/Gemini — is the actual Demo 1/4 verification per the phase file's exit
  criteria ("runs live end-to-end over the browser-audio demo transport"); CI cannot exercise
  real audio and should not pretend to.

---

## 13. Migrations

One migration, additive only (per `CLAUDE.md` §2.5's "every schema change is a migration,
generated and reviewed by eye"):

```
migrations/versions/2026-0X-XX_add_call_session_language.py
    - ALTER TABLE call_session ADD COLUMN language VARCHAR NOT NULL DEFAULT 'en'
```

No changes to `idempotency_record`, `audit_event`, or any Phase 1 table's constraints —
`send_secure_link`'s idempotency usage is data, not schema.

---

## 14. `requirements/base.txt` and `.env.example` additions

```
# requirements/base.txt additions
pipecat-ai
opentelemetry-sdk
opentelemetry-exporter-otlp
faster-whisper          # or: groq (hosted Whisper client) — pick one demo default, keep
                         # both adapter modules; only the chosen one's SDK is a hard dependency
google-generativeai      # or: groq — same "one hard default, both adapters exist" reasoning
piper-tts
aiohttp                  # voice_server.py's server framework (FastAPI/uvicorn stay in
                         # requirements too, for main.py — this is additive, not a replacement)
```

```
# .env.example additions
STT_PROVIDER=whisper
TTS_PROVIDER=piper
LLM_PROVIDER=gemini
TELEPHONY_PROVIDER=browser
GROQ_API_KEY=CHANGEME
GEMINI_API_KEY=CHANGEME
```

Per `.env.example`'s own Phase-0-era comment ("From Phase 2 onward, provider API keys go in
`.env`... only ever appear here as `CHANGEME`") — this phase is exactly the moment that
comment predicted.

---

## 15. CI updates

No new CI script — the two governance linters Phase 0 built
(`check_tool_allowlist.py`, `check_no_raw_prompt_concat.py`) already scan `src/voice/**/*.py`
generically; this phase is the first time they run against real, non-stub call sites
(`pipeline.py`'s `dispatch_tool_call(...)` call, `build_system_prompt(...)` call). Two new
negative-case fixtures under `tests/fixtures/` (matching the existing
`bad_tool_calls.py`/`bad_prompt_concat.py` pattern) assert the linters still catch a
deliberately-broken example *inside a file shaped like the real pipeline* — e.g. a fixture
function named `_build_system_prompt_bad` that f-string-concatenates a `caller_text`
variable, proving `check_no_raw_prompt_concat.py`'s pattern match still fires now that
`voice/` has real production-shaped code around the two Phase 0 stub files, not just the
stubs themselves.

`backend-ci.yml` needs no new step — both scripts are presumably already invoked (per
`phase-0-backend-spec.md` §657's `python scripts/ci/check_tool_allowlist.py` line); confirm
`check_no_raw_prompt_concat.py` has an equivalent CI invocation line and add one if Phase 0
only wired the tool-allowlist script.

---

## 16. Exit criteria traceability

| Exit criterion (phase file) | Mechanism |
|---|---|
| Demo 1 — Successful Status Update, live, browser transport | `voice_server.py` + `pipeline.py` + `browser_webrtc.py` adapter; verified by manual smoke test (§12) — right-party confirm → `AUTH_ANSWER`/`REQUEST_OTP` bridge → `get_claim_status` tool → `ASK_QUESTION` → close |
| Demo 4 — Authentication Failure, live | Existing `_run_authentication`/`_run_otp_challenge` branches (Phase 1, unchanged) driven by real STT/LLM-extracted `AUTH_ANSWER`/`OTP_ANSWER` intents instead of the test harness's scripted signals |
| Both demos pass in English and Arabic | `PromptContext.language` + Piper Arabic voice + Whisper/Groq Arabic transcription; §9's language-tracking logic; sequential EN→AR→mixed build order per §0.7 |
| Latency telemetry, P50/P95/P99 dashboards | §8's OpenTelemetry spans — dashboard consumption is Phase 3, spans exist and are queryable this phase |
| Barge-in / interruption | Pipecat's native VAD/interruption handling, wired at pipeline-assembly time in `voice/pipeline.py`'s `Pipeline(...)` construction (Pipecat-native, no custom code needed per the phase file's own wording) |
| DTMF fallback | §7 |
| Adversarial input tagging | §6/§0.4 |

---

## 17. Explicitly deferred to later phases

Same discipline as `phase-1-backend-spec.md` §17:

- Full `risk/` (fraud/vulnerability/legal-sensitivity routing), `privacy/` (PII redaction
  pipeline, DSAR), `knowledge/` (FAQ service beyond simple tool answers) — Phase 5. This
  phase's `guard.py`/adversarial-tagging and DTMF work are deliberately narrow slices that
  don't require these packages to exist yet (§0.4/§0.5).
- `CallTranscript`/`CallSummary`/`CustomerIntent`/`SentimentEvent` tables, the dashboard and
  its latency/analytics screens — Phase 3. This phase's OpenTelemetry spans and
  `CallSession.language` column are what Phase 3 reads from; no transcript persistence
  happens yet (raw STT output is used turn-by-turn and discarded, since spec §36 rule 17's
  redaction-before-persistence gate is Phase 5's `privacy/` pipeline, which doesn't exist —
  persisting *unredacted* transcripts now would be the actual rule violation).
- Real production STT/TTS/LLM/telephony vendors (Deepgram, ElevenLabs/Azure, Claude,
  UAE carrier trunk) — Phase 6's paid-vendor swap, a config change against the adapter
  Protocols this phase builds, per `IMPLEMENTATION_PLAN.md`'s migration checklist.
  Adversarial-resistance re-verification against Claude specifically is explicitly a Phase
  4/5/6 concern, not this phase's (phase file Notes section).
- Real PSTN answer detection (`classify_answer` activity) — stays the Phase 1
  `simulated_answer_result` stub; a real telephony vendor's ring/voicemail/busy
  classification is Phase 6 (§0.8).
- Ops-dashboard authentication, frontend work of any kind — unchanged from Phase 1's
  deferral; nothing in `frontend/` changes in this phase.
