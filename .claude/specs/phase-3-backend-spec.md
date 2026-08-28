# Phase 3 — Backend Engineering Spec (Operational Intelligence)

**Status:** Draft — ready for implementation
**Depends on:** [`phase-2-backend-spec.md`](./phase-2-backend-spec.md) (implemented, commit `2514289`)
**Spec references:** §28 (Conversation Event Log / Transcript PII Redaction Pipeline), §18
(Dissatisfaction Handling), §21 (AI Authority Matrix), §23 (Structured Call Outcome), §24
(Disposition Codes), §26 (Core DB Entities), §31 (MVP Dashboard Requirements), §35 Phase 3,
§36 rules 1/17/18/27
**Code-shape references:** `CLAUDE.md` §2.1 (`privacy/`, `audit/`, `reporting/`), §2.4
(Pydantic three-schema convention), §2.5 (SQLAlchemy insert-only tables), §2.6 (Temporal
activities as the idempotency boundary)
**Phase file:** [`phases/phase-3-operational-intelligence.md`](../../phases/phase-3-operational-intelligence.md)

---

## 0. Design decisions (read this before implementing)

### 0.1 What's actually greenfield vs. what Phase 1/2 left as a forward reference

`backend-explorer` confirmed the exact starting state:

- **`src/privacy/` does not exist at all.** No models, no `presidio-analyzer`/
  `presidio-anonymizer` in `requirements/base.txt` despite CLAUDE.md §2.1 naming them.
  Fully greenfield.
- **`src/reporting/` does not exist at all.** Fully greenfield.
- **`calls/models.py`'s own docstring (line 80) already flags this phase's job**: "not full
  per-turn history — that's `CallTranscript`'s job, Phase 3." There is currently **no
  transcript persistence path to audit for a redaction bypass** — `voice/pipeline.py`'s
  `_ConversationTapProcessor` reads `TranscriptionFrame.text` only to detect language
  changes and tag adversarial input; the text itself is never written to any table
  (`pipeline.py:180–184`). This phase is building the pipeline from nothing, not fixing an
  existing violation of spec §36 rule 17.
- `CallSummary`, `CustomerIntent`, `SentimentEvent` — none exist. `CustomerIntentSignal`
  (`calls/schemas.py:18–58`) is the closest existing thing (a Temporal signal payload with
  an `IntentName` literal, including `"DISSATISFIED"` already), but it is never persisted.

### 0.2 Resolving an apparent conflict: `phase-2-backend-spec.md` §17 vs. this phase's brief

`phase-2-backend-spec.md`'s deferred-work list says "Full `risk/` ..., `privacy/` (PII
redaction pipeline, DSAR) ... — Phase 5." Taken literally that would mean `privacy/`'s
redaction pipeline isn't this phase's job. But `phases/phase-3-operational-intelligence.md`
task 1 requires exactly that pipeline, and `phases/phase-5-security-compliance.md` task
"Privacy validation" explicitly says it will **re-verify Phase 3's redaction pipeline**
under adversarial input — i.e. Phase 5 assumes the pipeline already exists and hardens it.
Per `CLAUDE.md` §5 ("the spec wins on required behavior; the phase docs win on which
phase"), the phase files are authoritative on sequencing here, and they agree with each
other once read together: **the redaction pipeline itself is Phase 3; DSAR
(`PrivacyRequest`), `RecordingConsent`, and the `risk/` domain's legal-sensitivity/fraud/
vulnerability routing stay Phase 5.** `phase-2-backend-spec.md`'s note was shorthand that
conflated the whole `privacy/` package with the parts of it that really are Phase 5 — this
spec only builds the redaction pipeline + its own event log, nothing else in `privacy/`.

### 0.3 `voice/` still owns no tables — every new persisted fact lives in a DB-owning domain

CLAUDE.md is explicit that `voice/` is "NOT a database domain." Two real-time classifiers
get added this phase (`voice/sentiment.py`, and a latency tap) — both follow `voice/
guard.py`'s existing shape exactly: a pure, table-driven classification function with **no
I/O**, called from `voice/pipeline.py`, whose result is persisted by calling into `calls/`
(for transcript/summary/intent/sentiment/latency rows) or `privacy/` (for redaction event
rows) — never by `voice/` writing to the database itself.

### 0.4 Two write-path shapes, matching the precedent Phase 2 already established

`voice/pipeline.py` already has both shapes in production:

- **Direct activity-function calls, no `workflow.execute_activity`.** `record_audit_event`
  is imported and awaited directly from `_tag_if_adversarial` (`pipeline.py:191–202`) —
  legal because `voice_server.py`/`pipeline.py` run outside a workflow sandbox and activity
  functions are just async functions; there is no Temporal retry/idempotency guarantee on
  this path, which is acceptable for high-frequency, non-customer-impacting telemetry (a
  dropped audit-tag write is not a correctness bug).
- **`workflow.execute_activity(...)` from inside `calls/workflows.py`.** Used for every
  write that changes customer-facing state or must survive a workflow replay.

This phase's five new persisted fact types split across that same boundary:

| Fact | Written from | Shape | Why |
|---|---|---|---|
| `CallTranscript` (per turn) | `voice/pipeline.py` tap | direct activity call | high-frequency, per-turn; a dropped write loses one turn of transcript, not a customer-impacting fact |
| `PiiRedactionEvent` (per detection) | same call, inside the same activity | **idempotent**, via `src/idempotency.py` | `privacy/` is explicitly named in `CLAUDE.md` §4's idempotency non-negotiable — a retried transcript-turn write must never double-log a redaction detection |
| `SentimentEvent` (per turn) | `voice/pipeline.py` tap | direct activity call | telemetry only, no state change |
| `CustomerIntent` (per signal) | `calls/workflows.py` | `workflow.execute_activity` | already inside the workflow at the point a `CustomerIntentSignal` is consumed; just append one more activity call per existing signal-branch |
| `SentimentEvent` (`REPEATED_CONTACT`, call-start) | `calls/workflows.py::run()` | `workflow.execute_activity` | deterministic DB fact (prior attempt count), not a text classification — must be workflow-owned so it's replay-safe |
| `CallSummary` + final `SentimentEvent` | `calls/workflows.py::_finalize()` | `workflow.execute_activity` | runs once, at call end, alongside the existing `finalize_outcome`/`record_audit_event` activities already there |

### 0.5 The redaction pipeline sits inside the existing tap, not a new pipeline stage

Spec §28's diagram (`Audio → STT → Ephemeral Raw Buffer → PII Detection → Redaction/
Tokenization → Approved Redacted Transcript Store → Summary + Structured Events`) maps onto
code that already exists for everything up to "Ephemeral Raw Buffer": Pipecat's STT service
already emits `TranscriptionFrame`s into `_ConversationTapProcessor.process_frame`
(`pipeline.py:157–172`), and the frame's `.text` is exactly the ephemeral raw buffer — it
lives only as an in-memory Python string until this phase's new `_on_real_transcription`
addition calls `persist_transcript_turn` (§3.3 below), which runs PII detection, redaction,
and the store write in one activity, atomically. Nothing upstream of the tap changes.

### 0.6 Out-of-band LLM calls need a new, non-Pipecat client — confirmed via code inspection

`voice/adapters/llm/__init__.py::get_llm_service()` returns a Pipecat `LLMService`
instance wired into the live streaming pipeline's `LLMContext`/tool-calling machinery
(`pipeline.py:280`) — it is not a general "prompt in, text out" interface and has no
`base.py` Protocol (unlike `stt/`/`tts/`/`telephony/`). Conversation summarization and the
call-end sentiment pass run **out-of-band**, after the call, over structured facts already
in Postgres — not inside the live turn loop. Reusing `get_llm_service()` for this would mean
standing up a throwaway Pipecat pipeline just to make one completion call. This phase adds a
small new module instead:

```python
# src/voice/adapters/llm/completion.py
from typing import Protocol

class CompletionAdapter(Protocol):
    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict: ...
```

One provider module (`gemini_completion.py`, using the same `voice_settings.GEMINI_API_KEY`
the live pipeline already reads) satisfies it for the demo tier — config-selected off the
existing `voice_settings.LLM_PROVIDER`, so no new setting is needed. This keeps the "every
vendor is a `Protocol` + provider module" rule (`CLAUDE.md` §2.7) intact for a second,
narrower LLM use case without touching the live-pipeline adapter at all.

### 0.7 Conversation summaries never see raw transcript text — only structured, already-approved facts

The phase file is explicit: "only summarizing engine-approved facts + caller intents
already logged — never re-deriving new facts." The summarization prompt is therefore built
from `CallAttempt`'s structured outcome fields (`status_delivered`, `resolution`,
`verification_level`, disposition) plus the call's `CustomerIntent` rows — **not** from
`CallTranscript` rows, even though those are now redacted and available. This is a stronger
guarantee than "redact before it reaches the LLM": the LLM never receives free-text customer
speech at all for this task, closing off hallucination risk at the source rather than
depending on redaction to have caught everything. As defense in depth, the generated summary
text is still run back through `privacy/service.py::redact()` before being persisted (§4.2)
— belt and suspenders, in case the LLM echoes something structurally PII-shaped anyway.

### 0.8 Fixing the `DISSATISFIED` → `CLAIM_DELAY_ESCALATION` branch to actually check for a delay

`calls/workflows.py:645–665`'s existing `DISSATISFIED` branch creates a
`CLAIM_DELAY_ESCALATION` action **unconditionally** — it never checks whether the claim is
actually delayed. Spec §18's own example is explicit that this should be conditional: *"If
the system confirms a delay: [escalation offered]"* — implying the AI does **not** offer
escalation the same way when there's no real delay. Conveniently, `claims/models.py:71`
already has `MotorClaim.delay_flag: Mapped[bool]` — a real, already-computed fact, not
something this phase needs to derive. The fix (§5.2) is small and precise: gate
`CLAIM_DELAY_ESCALATION` on `claim.delay_flag`, falling back to `CLAIMS_TEAM_QUERY` (an
existing spec §25 action code with no current creator) when the claim isn't actually
delayed — this is the "never let an LLM/customer assumption substitute for the engine
checking real state" rule (`CLAUDE.md` §4) applied to a Phase 1/2 branch that predates
sentiment classification even existing to trigger it more broadly.

### 0.9 The latency-telemetry gap: OpenTelemetry spans are not a dashboard data source

`voice/telemetry.py` deliberately relies on Pipecat's own OTel tracing
(`PipelineWorker(enable_tracing=True)`) — by design, not persisted to Postgres. Spec §31
demands P50/P95/P99 **on the dashboard**, and this phase's exit criteria demands "every
chart traces to a real row in the database" — an OTel exporter is not that. Rather than
parsing spans back out of whatever OTLP backend receives them (adding an external
dependency this repo doesn't otherwise have), this phase adds one small, dedicated
persisted-sample table (`CallLatencySample`, §3.1) populated by a new lightweight tap
(§3.4) measuring end-of-speech → first-audio directly, independent of OTel. OpenTelemetry
tracing stays exactly as Phase 2 built it, for live observability; the new table is the
dashboard's actual data source. `voice_settings.TARGET_TURN_P95_MS` (already defined,
currently unused) becomes the threshold `reporting/service.py` compares the computed P95
against.

### 0.10 Being honest about metrics that will legitimately read zero this phase

Several spec §31 metrics have **no code path that can produce them yet**, and building
those code paths is out of this phase's scope (they belong to `risk/`, Phase 5, or real
telephony, Phase 6). Querying real tables for these and getting an honest `0` is correct
and is **not** the "placeholder/mocked numbers" the exit criteria forbids — a placeholder
would be a hardcoded frontend constant; a real query against a real, currently-empty result
set is an accurate reflection of the system today:

| Metric | Why it's honestly zero right now |
|---|---|
| Fraud/SIU referrals, vulnerable-customer referrals | `ActionCode.FRAUD_SIU_REVIEW_REQUEST`/`VULNERABLE_CUSTOMER_SUPPORT_REQUEST` exist as enum values (`actions/constants.py:25–26`) but nothing creates a `ClaimAction` with either code — `risk/` (fraud/vulnerability detection) doesn't exist yet, Phase 5 |
| Silent-call technical failure rate | `DispositionCode.SILENT_CALL_TECHNICAL_FAILURE` exists but nothing assigns it — real dead-air detection needs real telephony signal, not the browser-demo transport (Phase 6, same reasoning `phase-2-backend-spec.md` §17 gives for `classify_answer` staying a stub) |
| Rejected/unreachable/invalid-contact-number counts | `DispositionCode.CALL_REJECTED`/`NUMBER_UNREACHABLE`/`INVALID_CONTACT_NUMBER` exist but `classify_answer`'s stub only ever returns `HUMAN_ANSWERED`/`NO_ANSWER`/`VOICEMAIL`/`FAILED` — same Phase 6 telephony dependency |

**Model/STT/TTS failure rate is the one gap this phase does fix** (§5.3) — those vendors are
real in the demo tier (Whisper/Piper/Gemini can genuinely time out), so it's this phase's
job to make sure a Pipecat service error actually produces a `RuntimeFailureEvent` row,
unlike the telephony-dependent metrics above which have no real signal to capture yet.

**`CONCURRENT_CALL_CONFLICT` needs a different query than every other disposition metric.**
`campaigns/workflows.py:109–127`'s `_finalize_concurrent_conflict` never creates a
`CallAttempt` row at all (`CallSessionWorkflow` never started) — it only writes an
`AuditEvent` with `reason_code="CONCURRENT_CALL_CONFLICT"`, `correlation_id=call_job_id`.
`reporting/service.py`'s "concurrent-call conflicts prevented" metric must query
`AuditEvent`, not `CallAttempt.disposition_code` like every other operations-overview
number — documented explicitly in §6.2 so this isn't rediscovered the hard way as "always
zero."

---

## 1. Domain package layout — the Phase 2 → Phase 3 diff

```
backend/src/
├── privacy/                        # NEW — redaction pipeline + its own event log only
│   ├── __init__.py
│   ├── models.py                  # PiiRedactionEvent (insert-only)
│   ├── constants.py                 # PiiCategory enum
│   ├── scrubber.py                  # regex/checksum recognizers + Presidio wiring
│   └── service.py                    # redact() (pure) + record_redaction_events() (idempotent write)
├── reporting/                       # NEW — owns no tables; pure cross-domain aggregation
│   ├── __init__.py
│   ├── router.py                    # 6 read-only GET endpoints, one per §31 subsection + escalations
│   ├── schemas.py
│   └── service.py
├── calls/
│   ├── models.py                    # + CallTranscript, CallSummary, CustomerIntent,
│   │                                #   SentimentEvent, CallLatencySample (all insert-only)
│   ├── schemas.py                    # + *Read schemas for the four new read endpoints
│   ├── service.py                     # + record_transcript_turn, record_customer_intent,
│   │                                  #   record_sentiment_event, record_call_summary,
│   │                                  #   record_latency_sample, count_recent_attempts,
│   │                                  #   get_redacted_transcript (CLAUDE.md §1's own example)
│   ├── activities.py                   # + persist_transcript_turn, record_customer_intent,
│   │                                    #   record_sentiment_event, record_latency_sample,
│   │                                    #   generate_call_summary
│   ├── workflows.py                     # DISSATISFIED branch fix (§0.8); duration_seconds
│   │                                    #   fix (§5.4); new activity calls at 4 signal-wait
│   │                                    #   sites + run() start + _finalize()
│   ├── dependencies.py                   # unchanged (valid_call_attempt reused)
│   └── router.py                          # + GET /{call_id}/transcript, /summary, /intents, /sentiment
├── voice/
│   ├── sentiment.py                       # NEW — lexicon-based classifier, same shape as guard.py
│   ├── pipeline.py                         # tap gains transcript persistence, sentiment tagging,
│   │                                       #   AI-turn capture, latency measurement
│   └── adapters/llm/
│       ├── completion.py                    # NEW — CompletionAdapter Protocol (§0.6)
│       └── gemini_completion.py              # NEW — one provider implementation
├── main.py                                 # + reporting_router registration
└── worker.py                                # ALL_CALLS_ACTIVITIES gains 5 new entries — no new import needed
```

---

## 2. `privacy/` — the redaction pipeline

### 2.1 `privacy/constants.py`

```python
from enum import StrEnum

class PiiCategory(StrEnum):
    """Spec §28's minimum-detect list, verbatim."""
    EMIRATES_ID = "EMIRATES_ID"
    PASSPORT_NUMBER = "PASSPORT_NUMBER"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"
    IBAN = "IBAN"
    CARD_NUMBER = "CARD_NUMBER"
    OTP_PIN_CVV_PASSWORD = "OTP_PIN_CVV_PASSWORD"
    PHONE_NUMBER = "PHONE_NUMBER"
    EMAIL_ADDRESS = "EMAIL_ADDRESS"
    PHYSICAL_ADDRESS = "PHYSICAL_ADDRESS"
    POLICY_CLAIM_ID = "POLICY_CLAIM_ID"
    PERSON_NAME = "PERSON_NAME"
```

### 2.2 `privacy/models.py`

```python
class PiiRedactionEvent(Base):
    """Insert-only — the audit trail proving a category WAS caught and masked, per spec
    §28's 'make redaction failures observable and auditable.' Uses the same
    @enforce_insert_only decorator RuntimeFailureEvent/ComplaintSlaEvent already share
    (src/insert_only.py), not a hand-written copy of the three listeners."""
    __tablename__ = "pii_redaction_event"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    call_id: Mapped[str] = mapped_column(index=True)   # CallAttempt.id — not an FK, same
                                                         # reasoning as Escalation.call_id
    turn_index: Mapped[int]
    category: Mapped[PiiCategory] = mapped_column(SAEnum(PiiCategory, native_enum=False, length=32))
    detector: Mapped[str]    # "REGEX" | "CHECKSUM" | "PRESIDIO_NER"
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

Deliberately **no raw matched text, no character offsets** on this row — the event proves
*that* a category was found and masked in a given turn, which is all spec §28's "observable
and auditable" requirement needs; storing the actual matched PII in the audit-of-redaction
table would defeat the redaction it's auditing.

### 2.3 `privacy/scrubber.py` — the deterministic layer (always runs, language-independent)

Regex + checksum recognizers, each returning `(category, span)` matches over raw text:

| Category | Method |
|---|---|
| `IBAN` | `AE\d{2}\d{3}\d{16}` (UAE 23-char IBAN format) **+ mod-97 checksum** — a real, well-defined algorithm, not just a format guess |
| `CARD_NUMBER` | 13–19 contiguous digits **+ Luhn checksum** |
| `EMIRATES_ID` | `\d{3}-\d{4}-\d{7}-\d{1}` format match (no public checksum algorithm to verify against — documented as format-only) |
| `PHONE_NUMBER` | UAE mobile formats: `(?:\+971|0)5\d{8}` |
| `EMAIL_ADDRESS` | standard email pattern |
| `POLICY_CLAIM_ID` | `\b(POL|CLM)-[A-Z0-9-]+\b` (matches `claims/`'s own id format, e.g. `CLM-2026-001288`) |
| `OTP_PIN_CVV_PASSWORD` | a trigger-keyword window: if any of `otp\|code\|pin\|cvv\|password` (EN) / their Arabic equivalents appears within 3 tokens before a 3–6 digit run, mask the digit run — spec §36's "never log OTP/PIN/CVV/password" is the highest-severity rule in this codebase; this recognizer runs **first**, before anything else, and its match is masked unconditionally regardless of what any other layer decides |

Each match is replaced with `[<CATEGORY>_REDACTED]` (matching spec §28's own worked
example, `[EMIRATES_ID_REDACTED]`) before the text is handed to the NER layer.

### 2.4 Presidio layer (English only, documented limitation)

`AnalyzerEngine`/`AnonymizerEngine` (presidio-analyzer/presidio-anonymizer, per `CLAUDE.md`
§2.1's already-intended dependency, just never added to `requirements/base.txt` yet — §8
below) catch `PERSON_NAME`, `PHYSICAL_ADDRESS`, `DATE_OF_BIRTH` — categories the regex layer
structurally cannot find, since they have no fixed format. Presidio's default NLP engine
(spaCy `en_core_web_sm`) is **English-only**; running it against Arabic text either produces
garbage or nothing useful. `privacy/service.py::redact()` therefore only invokes the
Presidio pass when `language == "en"` — Arabic turns get the full deterministic layer
(§2.3, which is language-independent since it matches digit/format patterns, not natural
language) but no NER-based name/address masking. This is a **known, explicitly documented
gap**, not a silent omission — flagged again in §12 (Explicitly deferred) for Phase 5's
"re-verify under adversarial input" pass to specifically target.

### 2.5 `privacy/service.py`

```python
class RedactionResult(BaseModel):
    redacted_text: str
    detections: list[PiiCategory]   # categories found, deduplicated — not spans/counts

def redact(text: str, *, language: str) -> RedactionResult:
    """Pure — no I/O, no session. §2.3's deterministic pass always runs; §2.4's Presidio
    pass runs only when language == 'en'. Order matters: OTP/PIN/CVV/password masking runs
    unconditionally first."""


async def record_redaction_events(
    session: AsyncSession, *, call_id: str, turn_index: int, detections: list[PiiCategory],
) -> None:
    """Idempotent per CLAUDE.md §4's non-negotiable ('every actions/, complaints/,
    verification/, privacy/ write goes through src/idempotency.py'). Key is deterministic
    from (call_id, turn_index) — a retried persist_transcript_turn activity call must never
    double-log the same turn's detections."""
    for category in detections:
        await idempotent(
            session,
            key=f"pii-redaction:{call_id}:{turn_index}:{category.value}",
            correlation_id=call_id,
            operation_name="record_pii_redaction_event",
            payload={"call_id": call_id, "turn_index": turn_index, "category": category.value},
            operation=lambda category=category: _insert_event(session, call_id, turn_index, category),
        )
```

No router this phase — nothing yet consumes `PiiRedactionEvent` over HTTP (the RBAC-gated
`SecurityReviewPage`/compliance-review consumer needs `auth/`, which doesn't exist; see §12).

---

## 3. `calls/` additions — transcript, summary, intent, sentiment

### 3.1 `calls/models.py` — five new insert-only tables

```python
@enforce_insert_only
class CallTranscript(Base):
    __tablename__ = "call_transcript"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    call_attempt_id: Mapped[str] = mapped_column(ForeignKey("call_attempt.id"), index=True)
    turn_index: Mapped[int]
    speaker: Mapped[str]           # "CUSTOMER" | "AI"
    redacted_text: Mapped[str]     # ONLY ever the output of privacy/service.py::redact()
    language: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

@enforce_insert_only
class CallSummary(Base):
    __tablename__ = "call_summary"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    call_attempt_id: Mapped[str] = mapped_column(ForeignKey("call_attempt.id"), unique=True)
    summary_text: Mapped[str]      # redact()-passed LLM output, never raw
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

@enforce_insert_only
class CustomerIntent(Base):
    __tablename__ = "customer_intent"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    call_attempt_id: Mapped[str] = mapped_column(ForeignKey("call_attempt.id"), index=True)
    intent: Mapped[str]            # IntentName value — the durable record of CustomerIntentSignal
    topic: Mapped[str | None] = mapped_column(default=None)
    summary: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

@enforce_insert_only
class SentimentEvent(Base):
    __tablename__ = "sentiment_event"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    call_attempt_id: Mapped[str] = mapped_column(ForeignKey("call_attempt.id"), index=True)
    turn_index: Mapped[int | None] = mapped_column(default=None)  # None = call-level (start/end)
    sentiment: Mapped[str | None] = mapped_column(default=None)   # POSITIVE|NEUTRAL|NEGATIVE
    signal: Mapped[str | None] = mapped_column(default=None)      # spec §18's 7 signal names
    confidence: Mapped[float] = mapped_column(default=1.0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

@enforce_insert_only
class CallLatencySample(Base):
    __tablename__ = "call_latency_sample"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    call_attempt_id: Mapped[str] = mapped_column(ForeignKey("call_attempt.id"), index=True)
    turn_index: Mapped[int]
    latency_ms: Mapped[int]        # end-of-speech -> first-audio, spec §2.2.1
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

`sentiment`/`signal` are independent, both-optional columns rather than one combined field:
a plain polarity read (`NEGATIVE`, no named signal) happens on almost every turn a customer
speaks; a named signal (`DELAY_DISSATISFACTION` etc.) is rarer and only present when
`voice/sentiment.py` matches one of spec §18's specific patterns.

### 3.2 `calls/schemas.py` additions

Standard `Read` schemas (`ConfigDict(from_attributes=True)`) for all five models, plus:

```python
class CallTranscriptTurnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    turn_index: int
    speaker: str
    redacted_text: str
    language: str
    created_at: datetime
```

### 3.3 `calls/service.py` additions

```python
async def record_transcript_turn(
    session: AsyncSession, *, call_attempt_id: str, turn_index: int, speaker: str,
    redacted_text: str, language: str,
) -> CallTranscript: ...

async def get_redacted_transcript(session: AsyncSession, call_attempt_id: str) -> list[CallTranscript]:
    """The literal function CLAUDE.md §1's own worked example names
    (`calls/router.py`'s `get_call_transcript` route). Ordered by turn_index."""
    result = await session.execute(
        select(CallTranscript)
        .where(CallTranscript.call_attempt_id == call_attempt_id)
        .order_by(CallTranscript.turn_index)
    )
    return list(result.scalars())

async def record_customer_intent(session: AsyncSession, *, call_attempt_id: str,
    intent: str, topic: str | None, summary: str | None) -> CustomerIntent: ...

async def record_sentiment_event(session: AsyncSession, *, call_attempt_id: str,
    turn_index: int | None, sentiment: str | None, signal: str | None,
    confidence: float) -> SentimentEvent: ...

async def record_call_summary(session: AsyncSession, *, call_attempt_id: str,
    summary_text: str) -> CallSummary: ...

async def record_latency_sample(session: AsyncSession, *, call_attempt_id: str,
    turn_index: int, latency_ms: int) -> CallLatencySample: ...

async def count_recent_attempts(session: AsyncSession, *, customer_id: str, claim_id: str,
    since: datetime) -> int:
    """Deterministic REPEATED_CONTACT check — spec §31's 'repeated-contact customers,' §18's
    REPEATED_CONTACT signal. A DB count, never an LLM inference."""
    result = await session.execute(
        select(func.count(CallAttempt.id)).where(
            CallAttempt.customer_id == customer_id,
            CallAttempt.claim_id == claim_id,
            CallAttempt.attempted_at >= since,
        )
    )
    return result.scalar_one()
```

### 3.4 `calls/activities.py` additions

```python
class PersistTranscriptTurnInput(BaseModel):
    call_attempt_id: str
    turn_index: int
    speaker: Literal["CUSTOMER", "AI"]
    raw_text: str
    language: str

@activity.defn(name="persist_transcript_turn")
async def persist_transcript_turn(inp: PersistTranscriptTurnInput) -> None:
    """Called DIRECTLY from voice/pipeline.py (§0.4's first row) — not via
    workflow.execute_activity. Redaction (privacy/service.py::redact, pure) and both
    writes (CallTranscript + any PiiRedactionEvent rows) happen in one committed
    transaction: a redacted transcript row must never exist without its detection log
    committing alongside it, and vice versa."""
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        result = privacy_service.redact(inp.raw_text, language=inp.language)
        await calls_service.record_transcript_turn(
            session, call_attempt_id=inp.call_attempt_id, turn_index=inp.turn_index,
            speaker=inp.speaker, redacted_text=result.redacted_text, language=inp.language,
        )
        if result.detections:
            await privacy_service.record_redaction_events(
                session, call_id=inp.call_attempt_id, turn_index=inp.turn_index,
                detections=result.detections,
            )


class RecordCustomerIntentInput(BaseModel):
    call_attempt_id: str
    intent: str
    topic: str | None = None
    summary: str | None = None

@activity.defn(name="record_customer_intent")
async def record_customer_intent(inp: RecordCustomerIntentInput) -> None: ...
    # calls calls_service.record_customer_intent — called from calls/workflows.py via execute_activity


class RecordSentimentEventInput(BaseModel):
    call_id: str | None = None
    call_attempt_id: str
    turn_index: int | None = None
    sentiment: str | None = None
    signal: str | None = None
    confidence: float = 1.0

@activity.defn(name="record_sentiment_event")
async def record_sentiment_event(inp: RecordSentimentEventInput) -> None: ...
    # direct-call shape from voice/pipeline.py for per-turn rows (call_id set, no call_attempt_id
    # needed at the call site — call_attempt_id IS the call_id, same identifier throughout);
    # execute_activity shape from calls/workflows.py for the REPEATED_CONTACT / final-sentiment rows


class RecordLatencySampleInput(BaseModel):
    call_attempt_id: str
    turn_index: int
    latency_ms: int

@activity.defn(name="record_latency_sample")
async def record_latency_sample(inp: RecordLatencySampleInput) -> None: ...
    # direct-call from voice/pipeline.py's latency tap (§4.3)


class GenerateCallSummaryInput(BaseModel):
    call_attempt_id: str

@activity.defn(name="generate_call_summary")
async def generate_call_summary(inp: GenerateCallSummaryInput) -> dict[str, Any]:
    """Runs from calls/workflows.py::_finalize(), via execute_activity — after
    finalize_outcome so the structured facts it reads already exist. Builds the prompt from
    CallAttempt + CustomerIntent rows ONLY (§0.7) — never CallTranscript. Calls the
    out-of-band CompletionAdapter (§0.6), redacts the result defensively, writes CallSummary
    AND a call-level (turn_index=None) SentimentEvent capturing the final read."""
```

`ALL_CALLS_ACTIVITIES` (`calls/activities.py:536–554`) gains these five entries —
`worker.py` needs **no new import**, since it already imports the list, not individual
names (`worker.py:15`).

### 3.5 `calls/router.py` additions

Literally `CLAUDE.md` §1's own worked example, extended to the three sibling reads:

```python
@router.get("/{call_id}/transcript", response_model=list[CallTranscriptTurnRead])
async def get_call_transcript(
    attempt: Annotated[CallAttempt, Depends(valid_call_attempt)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[CallTranscript]:
    return await calls_service.get_redacted_transcript(db, attempt.id)

@router.get("/{call_id}/summary", response_model=CallSummaryRead | None)
@router.get("/{call_id}/intents", response_model=list[CustomerIntentRead])
@router.get("/{call_id}/sentiment", response_model=list[SentimentEventRead])
```

Uses the existing `valid_call_attempt` dependency (not a new `valid_call_session` one) —
every one of these four new tables is keyed by `call_attempt_id`, matching the router's
existing convention of keying everything off `call_id` == `CallAttempt.id`, not
`CallSession.id`. `CLAUDE.md`'s own snippet keys off `CallSession` illustratively; this
spec deliberately stays consistent with the router that's actually been built.

### 3.6 `calls/workflows.py` changes

**Four new activity-call sites**, one per `_wait_for_signal()` call that proceeds into
intent branching (`_run_right_party_check`, `_run_authentication`, `_run_otp_challenge`,
`_run_status_and_follow_up`) — factored into one helper to avoid four copies:

```python
async def _record_intent(self, attempt_id: str, signal: CustomerIntentSignal) -> None:
    await workflow.execute_activity(
        calls_activities.record_customer_intent,
        calls_activities.RecordCustomerIntentInput(
            call_attempt_id=attempt_id, intent=signal.intent,
            topic=signal.topic, summary=signal.summary,
        ),
        start_to_close_timeout=_ACTIVITY_TIMEOUT,
    )
```

Called as `if signal is not None: await self._record_intent(attempt_id, signal)`
immediately after each `signal = await self._wait_for_signal()`, before the existing
`if signal.intent == "..."` branch chain — this durably records every
`CustomerIntentSignal` the workflow ever consumes, independent of which branch handles it.

**`run()`** gains a call-start `REPEATED_CONTACT` check, right after `create_call_attempt`:

```python
recent_count = await workflow.execute_activity(
    calls_activities.count_recent_attempts_activity,   # thin wrapper over calls_service.count_recent_attempts
    CountRecentAttemptsInput(customer_id=inp.customer_id, claim_id=inp.claim_id,
                              since=_now() - timedelta(days=REPEATED_CONTACT_WINDOW_DAYS)),
    start_to_close_timeout=_ACTIVITY_TIMEOUT,
)
if recent_count >= REPEATED_CONTACT_THRESHOLD:
    await workflow.execute_activity(
        calls_activities.record_sentiment_event,
        calls_activities.RecordSentimentEventInput(
            call_attempt_id=attempt_id, signal="REPEATED_CONTACT", confidence=1.0,
        ),
        start_to_close_timeout=_ACTIVITY_TIMEOUT,
    )
```

`REPEATED_CONTACT_WINDOW_DAYS`/`REPEATED_CONTACT_THRESHOLD` join `voice/config.py` (or a
new small `calls/config.py`, matching `CLAUDE.md` §2.8's "a domain that genuinely needs its
own settings gets its own small `BaseSettings` subclass" — `calls/` doesn't have one yet;
two constants don't necessarily justify creating one, so a plain module-level constant in
`calls/constants.py` is the simpler, equally valid choice here).

**`__init__`** gains `self._attempted_at: datetime | None = None`, set to `_now()` at the
top of `run()` right before `create_call_attempt` — the missing piece for §5.4's
`duration_seconds` fix.

**`_finalize()`** gains, after the existing `finalize_outcome`/`record_audit_event` calls:

```python
await workflow.execute_activity(
    calls_activities.generate_call_summary,
    calls_activities.GenerateCallSummaryInput(call_attempt_id=attempt_id),
    start_to_close_timeout=_BACKEND_ACTIVITY_TIMEOUT,   # LLM call — same generous timeout
    retry_policy=_BACKEND_RETRY_POLICY,                 # class as deliver_status uses
)
```

Deliberately best-effort-only in this first cut: **no branch on failure** — if summary
generation fails after retries, the workflow still returns its `CallSessionOutput`
normally. A missing `CallSummary` for one call is a dashboard gap, not a customer-impacting
failure, and must never block or delay the call's own finalization/disposition.

### 3.7 The `DISSATISFIED` branch fix (§0.8, concretely)

```python
if signal.intent == "DISSATISFIED":
    claim = await workflow.execute_activity(
        calls_activities.get_claim_delay_flag,   # thin new activity: SELECT delay_flag FROM motor_claim
        GetClaimDelayFlagInput(claim_id=inp.claim_id),
        start_to_close_timeout=_ACTIVITY_TIMEOUT,
    )
    action_code = "CLAIM_DELAY_ESCALATION" if claim.delay_flag else "CLAIMS_TEAM_QUERY"
    await workflow.execute_activity(
        calls_activities.create_action,
        calls_activities.CreateActionInput(
            key=self._next_action_key(inp.call_id), correlation_id=inp.call_id,
            claim_id=inp.claim_id, action_code=action_code,
            summary=signal.summary or "Customer dissatisfied with delay",
            source_call_id=attempt_id,
        ),
        start_to_close_timeout=_ACTIVITY_TIMEOUT,
    )
    # ... unchanged from here (resolution = "ACTION_CREATED", _finalize(...))
```

---

## 4. `voice/` additions

### 4.1 `voice/sentiment.py` — same shape as `voice/guard.py`

```python
class SentimentClassification(BaseModel):
    sentiment: Literal["POSITIVE", "NEUTRAL", "NEGATIVE"]
    signal: str | None   # one of spec §18's 7 signal names, or None
    confidence: float

def classify_sentiment(text: str) -> SentimentClassification:
    """Pure, table-driven lexicon match — EN + AR phrase lists, same construction as
    guard.py's GUARD_PATTERNS. Detects NEGATIVE_SENTIMENT / DELAY_DISSATISFACTION /
    SERVICE_FAILURE / CUSTOMER_DISPUTE from wording alone. Deliberately does NOT attempt
    REPEATED_CONTACT (a DB count, §3.3/§3.6) or FORMAL_COMPLAINT_REQUEST/HUMAN_REQUEST (already
    covered by voice/tools.py's register_complaint/create_escalation/warm_transfer tool
    calls — duplicating them here would risk a second, inconsistent complaint/escalation
    creation path)."""
```

### 4.2 `_ConversationTapProcessor` changes (`voice/pipeline.py`)

`CallPipelineContext` gains `self.turn_index = 0`.

`_on_real_transcription` (customer turns) gains, alongside the existing adversarial tag:

```python
async def _on_real_transcription(self, frame: TranscriptionFrame) -> None:
    if frame.language and str(frame.language) != self._ctx.current_language:
        await self._persist_language(str(frame.language))
    await self._refresh_system_prompt()
    await self._tag_if_adversarial(frame.text)
    await self._persist_turn("CUSTOMER", frame.text)
    await self._tag_sentiment(frame.text)

async def _persist_turn(self, speaker: str, text: str) -> None:
    from src.calls.activities import PersistTranscriptTurnInput, persist_transcript_turn
    turn_index = self._ctx.turn_index
    self._ctx.turn_index += 1
    await persist_transcript_turn(PersistTranscriptTurnInput(
        call_attempt_id=self._ctx.call_id, turn_index=turn_index, speaker=speaker,
        raw_text=text, language=self._ctx.current_language,
    ))

async def _tag_sentiment(self, text: str) -> None:
    from src.calls.activities import RecordSentimentEventInput, record_sentiment_event
    from src.voice import sentiment
    result = sentiment.classify_sentiment(text)
    await record_sentiment_event(RecordSentimentEventInput(
        call_attempt_id=self._ctx.call_id, turn_index=self._ctx.turn_index - 1,
        sentiment=result.sentiment, signal=result.signal, confidence=result.confidence,
    ))
    # DELAY_DISSATISFACTION is the one signal that must also reach the workflow — as a
    # SAFETY NET alongside the LLM's own conversational handling, not a replacement for it:
    # the workflow's existing DISSATISFIED branch (§3.7) is what actually decides whether a
    # delay is confirmed and what action gets created.
    if result.signal == "DELAY_DISSATISFACTION":
        from src.calls.workflows import CallSessionWorkflow
        from src.calls.schemas import CustomerIntentSignal
        await self._ctx.workflow_handle.signal(
            CallSessionWorkflow.customer_utterance,
            CustomerIntentSignal(intent="DISSATISFIED", summary=text[:500]),
        )
```

A second, symmetric assistant-turn tap persists `speaker="AI"` rows from whichever
Pipecat frame type carries the LLM's finalized output text ahead of TTS (Pipecat's exact
frame class for this — `TextFrame`/`LLMTextFrame`/`TTSTextFrame` depending on package
version — needs confirming against the pinned `pipecat-ai==1.8.1` at implementation time;
the phase-2 spec hedged the same way for Pipecat-internal specifics it hadn't yet pinned
down). It calls the same `_persist_turn("AI", text)` — no sentiment tagging on AI-authored
turns, since sentiment classification is about the *customer's* emotional state.

### 4.3 Latency tap

A new, small `FrameProcessor` (or an extension of the existing tap — implementation's
choice) records `workflow.now()`-independent wall-clock timestamps: the end of a
`TranscriptionFrame` (STT finished) to the first `TTSAudioRawFrame` pushed afterward
(first audio out). On each measured turn:

```python
from src.calls.activities import RecordLatencySampleInput, record_latency_sample
await record_latency_sample(RecordLatencySampleInput(
    call_attempt_id=ctx.call_id, turn_index=ctx.turn_index - 1,
    latency_ms=int((first_audio_at - end_of_speech_at).total_seconds() * 1000),
))
```

Direct activity call, same shape as every other per-turn write in this phase — never
blocks the audio path itself (fired after the audio frame is already pushed downstream,
not awaited inline in the frame-processing critical path).

---

## 5. `reporting/` — read-only cross-domain aggregation

`reporting/` owns **no tables** — every query reads `CallAttempt`, `CallLatencySample`,
`SentimentEvent`, `CustomerIntent`, `ClaimAction`, `Complaint`, `Escalation`, `Callback`,
`CallJob`, and (for the one exception in §0.10) `AuditEvent` directly. This mirrors how
`claims/` has no mutation-owning frontend hooks per `CLAUDE.md` §3.3 — a domain can be
entirely reads.

### 5.1 `reporting/router.py` — six endpoints, one per §31 subsection + escalations

```python
router = APIRouter()

@router.get("/operations-overview", response_model=OperationsOverviewRead)
async def operations_overview(since: datetime, until: datetime, db=Depends(get_db)): ...

@router.get("/outcome-funnel", response_model=OutcomeFunnelRead)
async def outcome_funnel(since: datetime, until: datetime, db=Depends(get_db)): ...

@router.get("/no-answer-analytics", response_model=NoAnswerAnalyticsRead)
async def no_answer_analytics(since: datetime, until: datetime, db=Depends(get_db)): ...
    # also satisfies the phase file's "attempt analytics" line item — spec §31 itself lists
    # "attempt number vs answer rate" under No-Answer Analytics, not as a separate section

@router.get("/status-analytics", response_model=list[StatusAnalyticsRow])
async def status_analytics(since: datetime, until: datetime, db=Depends(get_db)): ...

@router.get("/customer-experience", response_model=CustomerExperienceRead)
async def customer_experience(since: datetime, until: datetime, db=Depends(get_db)): ...

@router.get("/escalation-analytics", response_model=EscalationAnalyticsRead)
async def escalation_analytics(since: datetime, until: datetime, db=Depends(get_db)): ...
    # the phase file's separate "escalation analytics" line item — spec §31 has no
    # dedicated Escalation section, so this endpoint's shape (queue depth by status, reason
    # breakdown, warm-transfer volume) is this spec's own design, not a literal spec quote
```

`since`/`until` are **required**, not defaulted — an implicit "last 24h" default would
silently hide a stale/empty range from whoever's building the frontend against this API;
the frontend's `DashboardPage`/`AnalyticsPage` (Phase 3 frontend, separate spec) supply an
explicit range from a date-picker.

No auth dependency on any of these — `src/auth/` does not exist yet (confirmed: no
`backend/src/auth` directory at all). Every other router in this codebase is equally
unauthenticated today; this is not a regression this phase introduces, and RBAC-gating
(`CLAUDE.md` §3.4's `RoleGate`) is a frontend-and-backend concern that arrives together
whenever `auth/` is actually built.

### 5.2 `reporting/service.py` — the query-to-metric map (the part worth getting exactly right)

| §31 metric | Query |
|---|---|
| calls scheduled | `count(CallJob)` in range |
| calls attempted | `count(CallAttempt)` in range |
| human answer rate | `count(customer_reached=True) / count(*)` |
| right-party contact rate | `count(right_party=True) / count(customer_reached=True)` |
| verification success rate | `count(verified=True) / count(right_party=True)` |
| statuses delivered | `count(status_delivered IS NOT NULL)` |
| AI-contained/resolved calls | `count(resolution='FULLY_RESOLVED_BY_AI')` |
| actions/complaints/escalations/callbacks created | `count(ClaimAction)` / `count(Complaint)` / `count(Escalation)` / `count(Callback)`, each independently ranged by their own `created_at` |
| no-answer rate | `count(disposition_code='NO_ANSWER') / count(*)` |
| avg call duration | `avg(duration_seconds)` — **requires §5.4's fix**, currently always `NULL` |
| P50/P95/P99 latency | `percentile_cont(0.5\|0.95\|0.99) WITHIN GROUP (ORDER BY latency_ms)` over `CallLatencySample` |
| silent-call / backend / model-STT-TTS failure rates | `RuntimeFailureEvent` grouped by `component` (§5.3 extends which components get recorded) — **not** `DispositionCode`, since those specific codes are never assigned (§0.10) |
| DTMF fallback rate | `count(disposition_code='DTMF_FALLBACK_ACTIVATED') / count(*)` |
| **concurrent-call conflicts prevented** | `count(AuditEvent WHERE reason_code='CONCURRENT_CALL_CONFLICT')` — **not** `CallAttempt` (§0.10) |
| dropped-call rate | `count(disposition_code IN ('CALL_DROPPED_PRE_AUTH','CALL_DROPPED_POST_AUTH')) / count(*)` |
| OTP lockouts/rate limits | `count(disposition_code IN ('OTP_LOCKED','OTP_ATTEMPTS_EXCEEDED'))` |
| fraud/SIU, vulnerable-customer referrals | `count(ClaimAction WHERE action_code IN (...))` — honestly zero today (§0.10) |

Outcome funnel stages map directly onto `CallAttempt` boolean/nullable fields already in
`CallAttempt` (`customer_reached` → `right_party` → `verified` → `status_delivered IS NOT
NULL` → `resolution='FULLY_RESOLVED_BY_AI'`), each stage's count being a `WHERE` filter one
step stricter than the last — a single query with conditional aggregates, not five separate
round trips.

Customer Experience Analytics reads `SentimentEvent`: "initial sentiment" = the row with
`MIN(turn_index)` per call among rows with `turn_index IS NOT NULL`; "final sentiment" = the
call-level (`turn_index IS NULL`, `signal IS NULL`) row §3.6's `generate_call_summary`
activity writes; "dissatisfaction rate" = calls with at least one `signal IN
('NEGATIVE_SENTIMENT','DELAY_DISSATISFACTION','SERVICE_FAILURE')` row; "repeated-contact
customers" = distinct `customer_id` with a `signal='REPEATED_CONTACT'` row; "calls requiring
humans" = `count(disposition_code='SUCCESS_HUMAN_TRANSFER')`.

### 5.3 Extending `RuntimeFailureEvent` to cover STT/LLM/TTS, not just `BACKEND`

`with_runtime_recovery` (`calls/activities.py:86–113`) is currently applied only to
`deliver_status` (`component="BACKEND"`). This phase adds a lightweight equivalent inside
`voice/pipeline.py`'s pipeline-error handling: Pipecat's `ErrorFrame` (or the specific
service exception types `pipecat-ai==1.8.1` raises — confirm exact type at implementation
time) triggers a direct call to a new `calls_activities.record_runtime_failure_event`
(a thin public wrapper around the existing private `_record_runtime_failure`,
`calls/activities.py:69–83`, now needed from outside that module) with
`component IN ("STT","LLM","TTS")` depending on which service raised. This is the one
concrete fix from §0.10's table — everything else there stays deferred.

### 5.4 The `duration_seconds` fix

`FinalizeOutcomeInput.duration_seconds` (`calls/activities.py:212`) and
`calls_service.finalize_outcome`'s matching parameter (`calls/service.py:73`) already
exist and are already wired end-to-end into the `CallAttempt` column — the gap is only that
`calls/workflows.py::_finalize()` never populates the field when constructing
`FinalizeOutcomeInput` (§0's read of `workflows.py:149–163` confirms it's omitted, silently
defaulting to `None`). The fix is one line, using the `self._attempted_at` this phase adds
(§3.6):

```python
duration_seconds=(
    int((_now() - self._attempted_at).total_seconds()) if self._attempted_at else None
),
```

added to `_finalize()`'s existing `FinalizeOutcomeInput(...)` construction.

---

## 6. Testing strategy

Same "no real audio/LLM in CI" discipline Phase 2 established:

- **`tests/unit/test_scrubber.py`**: table-driven over spec §28's minimum-detect list plus
  adversarial cases — a spoken-out-loud Emirates ID/IBAN/card number/OTP **must never
  survive** into `redact()`'s output; asserts the exact `[<CATEGORY>_REDACTED]` replacement
  shape. This is the redaction-specific analog of `test_guard_classifier.py`'s pattern, and
  the single most important test this phase adds (spec §36 rule 17 is the highest-severity
  rule a missed case here could violate).
- **`tests/unit/test_iban_checksum.py`** / **`test_luhn_checksum.py`**: valid vs.
  deliberately-invalid checksum inputs, confirming the checksum recognizers don't just
  pattern-match digit counts.
- **`tests/unit/test_sentiment_classifier.py`**: table-driven over spec §18's example
  phrases (EN + AR) for each of the 4 lexicon-detectable signals, plus benign utterances
  asserting no false positive.
- **`tests/unit/test_dissatisfied_branch_delay_gate.py`**: `resolve_disposition`-adjacent —
  a `DISSATISFIED` signal against a claim with `delay_flag=False` must produce
  `CLAIMS_TEAM_QUERY`, not `CLAIM_DELAY_ESCALATION`; `delay_flag=True` must still produce
  `CLAIM_DELAY_ESCALATION` (regression guard on the existing, already-tested branch).
- **`tests/unit/test_pii_redaction_idempotency.py`**: two `record_redaction_events` calls
  with the identical `(call_id, turn_index)` key produce exactly one `PiiRedactionEvent`
  row per category — the idempotency non-negotiable, mechanically checked.
- **`tests/integration/test_phase3_transcript_pipeline_e2e.py`**: drives
  `persist_transcript_turn` directly (same "stand in for the real pipeline" harness style
  `test_phase2_pipeline_signal_bridge.py` established) with a scripted turn containing a
  fabricated Emirates ID, asserting the persisted `CallTranscript.redacted_text` never
  contains the raw digits and a matching `PiiRedactionEvent` row exists.
- **`tests/integration/test_phase3_reporting_queries_e2e.py`**: seeds a handful of
  `CallAttempt`/`SentimentEvent`/`CallLatencySample` rows directly, hits each of the six
  `reporting/router.py` endpoints, and asserts the returned numbers match hand-computed
  expectations — this is what proves §5.2's query map is actually correct, not just
  plausible-looking SQL.
- **`tests/unit/test_call_duration_populated.py`**: a full scripted `CallSessionWorkflow`
  run (reusing the Phase 1/2 fake-signal harness) asserts `CallAttempt.duration_seconds` is
  non-`None` and roughly matches the Temporal test environment's simulated elapsed time.
- A **live manual smoke test** (not CI): a full demo call over real Whisper/Piper/Gemini,
  followed by manually inspecting the persisted `call_transcript` rows for that call — the
  phase file's own Notes section calls this out as "cheap now, expensive to discover missing
  during Phase 5."

---

## 7. Migrations

Chains from `9e2f4a7c1b6d` (`2026-08-28_add_call_session_language.py`, current HEAD):

```
migrations/versions/2026-08-29_phase3_privacy_pii_redaction_event.py
    - CREATE TABLE pii_redaction_event (...)
    - REVOKE UPDATE, DELETE ON pii_redaction_event FROM <app_role>   # 3rd insert-only layer,
                                                                       same pattern as the
                                                                       existing insert-only grants

migrations/versions/2026-08-29_phase3_calls_transcript_summary_intent_sentiment.py
    - CREATE TABLE call_transcript (...)
    - CREATE TABLE call_summary (...)
    - CREATE TABLE customer_intent (...)
    - CREATE TABLE sentiment_event (...)
    - CREATE TABLE call_latency_sample (...)
    - REVOKE UPDATE, DELETE ON <all five> FROM <app_role>
```

Two migrations (not five/six individually) — `privacy/` and `calls/` are each one
committed unit of schema change per domain, matching how `2026-08-27_phase1_calls_
verification_actions_complaints.py` already bundled multiple `calls/`-adjacent tables into
one migration rather than one-per-table. No changes to any Phase 0–2 table.

---

## 8. `requirements/base.txt` and `.env.example` additions

```
# requirements/base.txt additions — Phase 3, Operational Intelligence
presidio-analyzer==2.2.360
presidio-anonymizer==2.2.360
spacy==3.8.7           # presidio-analyzer's NLP engine dependency
# en_core_web_sm installed via a separate `python -m spacy download` step (a model
# download, not a pip package) — document in backend/README, same as any spaCy project
```

No new `.env.example` entries — the out-of-band `CompletionAdapter` (§0.6) reuses
`voice_settings.GEMINI_API_KEY`/`LLM_PROVIDER`, already present since Phase 2.

---

## 9. CI updates

No new governance linter — Phase 0's two scripts
(`check_tool_allowlist.py`/`check_no_raw_prompt_concat.py`) already scan `src/voice/**/*.py`
generically and this phase adds no new LLM-prompt-construction call site outside the
pattern they already cover (`generate_call_summary`'s prompt is built from structured
Pydantic fields via `CompletionAdapter.complete_json`, not raw f-string concatenation of
caller-supplied text — the same discipline `build_system_prompt` already follows).

One new negative-fixture-style test worth adding to the existing `tests/fixtures/` pattern:
**`tests/fixtures/bad_transcript_persistence.py`** — a deliberately-broken example function
that calls `calls_service.record_transcript_turn` directly with **unredacted** raw text
(bypassing `privacy_service.redact()` entirely), and a matching
**`tests/unit/test_no_unredacted_transcript_writes.py`** that grep-asserts every real call
site of `record_transcript_turn` in `src/` passes through `redact()`'s result first — the
mechanical enforcement of spec §36 rule 17, the same style Phase 0's `check_no_raw_prompt_
concat.py` already established for a different rule.

---

## 10. Exit criteria traceability

| Exit criterion (phase file) | Mechanism |
|---|---|
| Every §31 Operations Overview metric populated from real data | §5.2's query map; §5.4 fixes the one currently-`NULL` field (`duration_seconds`) that would otherwise silently break "avg call duration" |
| Outcome Funnel with conversion at each stage | §5.2, single conditional-aggregate query over `CallAttempt` |
| No-Answer Analytics (incl. attempt-number-vs-answer-rate) | §5.2 `/no-answer-analytics` |
| Status Analytics (question/escalation rate by status) | `status_delivered` grouped against `question_resolved`/escalation-flagged `CallAttempt` rows |
| Customer Experience Analytics | §5.2, reads `SentimentEvent` (new this phase) |
| "None of the above are placeholder/mocked numbers" | §0.10 documents exactly which sub-metrics are honestly zero and why, rather than faking non-zero data — every number, including the zeros, traces to a real query |
| Redaction pipeline built and tested against real calls, sample manually inspected | §2 (pipeline), §6 (`test_scrubber.py` + the live smoke test), phase file Notes |
| `calls/` transcript-persistence path cannot accept raw STT output directly | §3.4's `persist_transcript_turn` activity — `redact()` runs before the only `INSERT` into `call_transcript` exists in the codebase (§9's fixture/linter-style test makes this mechanically checked, not just reviewed by eye) |
| Conversation summaries from engine-approved facts + logged intents only, never re-derived | §0.7, §3.4 `generate_call_summary` |
| Sentiment/dissatisfaction classification feeding §18 signals | §4.1 `voice/sentiment.py`; §3.7 fixes the one branch that was already wrong before this phase's classifier could even feed it correctly |

---

## 11. Explicitly deferred to later phases

Same discipline as `phase-2-backend-spec.md` §17:

- **`PrivacyRequest` (DSAR routing), `RecordingConsent`, `pii_redaction_event`'s
  RBAC-gated review endpoint** — Phase 5, per §0.2's resolved reading of the two phase
  files. This phase's `privacy/` package is deliberately narrow: the redaction pipeline and
  its own append-only event log, nothing else `CLAUDE.md`'s `privacy/` bullet lists.
- **`risk/` (fraud/vulnerability/legal-sensitivity routing), legal hold** — Phase 5, per
  `phase-2-backend-spec.md` §17 (unchanged by this phase) and confirmed again by §0.10's
  "fraud/SIU referrals will read zero" honesty note.
- **Presidio-based NER redaction for Arabic turns** — a documented gap (§2.4), not silently
  dropped; Phase 5's "re-verify Phase 3's redaction pipeline under adversarial input" task
  is the natural place to decide whether an Arabic-capable NER model is needed before
  production, or whether the deterministic regex/checksum layer (which IS
  language-independent) is judged sufficient for the categories that matter most (IDs,
  IBANs, cards, OTPs — all digit/format-based, all already covered in Arabic).
- **`SILENT_CALL_TECHNICAL_FAILURE`, `CALL_REJECTED`, `NUMBER_UNREACHABLE`,
  `INVALID_CONTACT_NUMBER` disposition assignment** — needs real telephony signal the
  browser-demo transport cannot produce; Phase 6, same reasoning `phase-2-backend-spec.md`
  §17 already gives for `classify_answer` staying a stub.
- **Ops-dashboard authentication / RBAC (`auth/`)** — still doesn't exist; this phase's new
  read endpoints are unauthenticated, consistent with every existing endpoint. Frontend
  Phase 3 work (`DashboardPage`, `AnalyticsPage`, `reportingService.js`) is a separate spec.
- **Real production STT/TTS/LLM vendors, real PSTN telephony** — unchanged, Phase 6's
  paid-vendor swap against the adapter Protocols Phase 2 already built (and this phase's
  `CompletionAdapter`, §0.6, extends the same way).
