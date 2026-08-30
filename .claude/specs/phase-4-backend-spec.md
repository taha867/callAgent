# Phase 4 — Backend Engineering Spec (Demo Hardening & Governed Regression)

**Status:** Draft — ready for implementation
**Depends on:** [`phase-3-backend-spec.md`](./phase-3-backend-spec.md) (implemented), [`phase-3-frontend-spec.md`](./phase-3-frontend-spec.md)
**Spec references:** §35 Phase 4 (adversarial scenario checklist), §29 (Eight Mandatory Demo
Journeys), §30 (Ninth Technical Demo — No Answer), §36 (Non-Negotiable Engineering Rules),
§2.2.2 (LLM cannot create its own authority), §4.1 (distributed voice lock), §10.6.4
(idempotency)
**Code-shape references:** `CLAUDE.md` §2.1 (domain-package layout), §2.4 (Pydantic
three-schema convention), §2.5 (SQLAlchemy mutable-vs-insert-only tables), §2.6 (Temporal
test environments)
**Companion framework:** Judgment Compiler two-strike governance pattern
(`IMPLEMENTATION_PLAN.md` §0, `phases/phase-4-demo-hardening.md`)
**Phase file:** [`phases/phase-4-demo-hardening.md`](../../phases/phase-4-demo-hardening.md)

---

## 0. Design decisions (read this before implementing)

### 0.1 Phase 4 is not a new-CRUD-entity phase — it's a governance + regression phase, and the code shape has to say so

Phases 0–3 each added domain packages that model *insurance/call-center* concepts (claims,
campaigns, complaints, reporting). Phase 4 adds exactly **one** new domain package —
`src/qa/` — and it models the *engineering process itself* (defects found during hardening,
demo-journey pass/fail runs). This is a deliberate, narrow scope: per `phases/
phase-4-demo-hardening.md`, the actual work of this phase is running the 9 demo journeys
against the adversarial checklist and fixing what breaks in the domains that already exist
(`voice/guard.py`, `calls/workflows.py`, etc.) — `qa/` exists only to make that work
**measurable and reviewable** (the phase file's own exit criteria: "the defect log itself
exists and is reviewable... not a subjective judgment").

### 0.2 `backend-explorer` confirmed the exact starting state — no scripted-conversation harness exists yet

- `backend/tests/unit/` (27 files) and `backend/tests/integration/` (18 files) exist,
  pytest-asyncio, with a real Temporal test environment already wired in
  `tests/integration/conftest.py` (`temporal_env` — real Temporal or
  `WorkflowEnvironment.start_local()`; `temporal_time_skipping_env` —
  `WorkflowEnvironment.start_time_skipping()`, used by `campaigns.RetrySchedulerWorkflow`/
  the complaint SLA monitor). This phase's new test suite reuses these fixtures — it does
  not invent a second Temporal test harness.
- **There is no way today to drive a full Pipecat pipeline run from a canned transcript.**
  `src/voice/adapters/stt/__init__.py` only wires `whisper`/`groq_whisper` — no `test`/`fake`
  STT provider exists. The existing precedent (`tests/integration/
  test_phase2_pipeline_signal_bridge.py`) calls `dispatch_tool_call(...)` directly, "standing
  in for `voice/pipeline.py`'s LLM-tool-use turn... without needing a real STT/LLM/TTS
  adapter in the loop." **This phase's scripted-conversation suite follows that exact
  precedent** — it drives `voice/guard.py::classify_adversarial()` and `voice/tools.py`'s
  tool dispatch directly with scripted customer-utterance text, plus workflow signals, and
  asserts on `CallState`/`DispositionCode`/`AuditEvent` outcomes. It does **not** attempt a
  real-audio, real-STT, real-Pipecat-transport end-to-end run — building that is out of
  scope for a $0-cost demo hardening phase and would require new STT/TTS/telephony test
  infrastructure that spec §35 never asks for. If a future phase needs true audio-in
  end-to-end coverage, that is a `voice/adapters/stt/test.py` fake-adapter task, tracked as a
  deferred item (§8), not silently assumed to exist here.
- `voice/guard.py`'s own docstring already names this phase: "not the hardened
  adversarial-resistance work Phase 4/5 re-runs against Claude" — i.e. the file that most
  needs this phase's attention already flags itself. `classify_adversarial()` is a flat
  12-phrase substring match today.
- `calls/constants.py`'s `FUTURE_GLOBAL_INTERRUPTS` frozenset already lists 9 signals as
  explicitly not-yet-handled at the workflow level, including `ADVERSARIAL_INPUT_DETECTED`
  itself, `CUSTOMER_VULNERABILITY_INDICATED`, `FRAUD_SUSPECTED`,
  `LEGAL_SENSITIVITY_DETECTED`, `DSAR_OR_PRIVACY_RIGHTS_REQUEST`,
  `COMMUNICATION_SUPPRESSION_REQUEST`, `ACCESSIBILITY_REQUIREMENT_DETECTED`,
  `RECORDING_CONSENT_REFUSED`, `SAFETY_OR_SECURITY_ESCALATION`. `src/risk/` and
  `src/knowledge/` don't exist at all; `src/privacy/` only has the redaction pipeline
  (DSAR/`RecordingConsent`/the whole `risk/` domain are Phase 5 per `phase-3-backend-
  spec.md` §0.2).

### 0.3 Consequence: not all 32 adversarial-checklist items can genuinely pass this phase — the spec must say which, not silently assume

Cross-referencing the phase file's checklist (`phases/phase-4-demo-hardening.md` lines
35–70) against what `backend-explorer` found actually wired:

| Checklist item | Status this phase | Why |
|---|---|---|
| DSAR request | **Blocked on Phase 5** | No `PrivacyRequest` model/service exists |
| Child/minor appears to answer | **Blocked on Phase 5** | No detection code path exists anywhere |
| "Never call me again" (suppression) | **Blocked on Phase 5** | No `CommunicationSuppression` handling exists |
| Refuses recording/transcription consent | **Blocked on Phase 5** | No `RecordingConsent` model exists |
| Fraud/SIU signal, covert routing | **Blocked on Phase 5** | `src/risk/` doesn't exist |
| Vulnerable-customer disclosure | **Blocked on Phase 5** | `src/risk/` doesn't exist |
| Legal-sensitivity + evidence preservation | **Blocked on Phase 5** | `src/risk/` doesn't exist |
| SIM-swap / high-risk number change | **Blocked on Phase 5** | No signal source exists |
| Ramadan/holiday blackout window | **Testable this phase, but needs seed data** | `BusinessContactCalendar`/`is_within_contact_window()` exist (`telephony/models.py`, `telephony/service.py`) but no rows are seeded — it returns `True` for every unseeded date today |
| Everything else (24 items) | **Testable today** | Underlying mechanism already exists: DTMF fallback (`voice/dtmf.py`, `MAX_CONSECUTIVE_LOW_STT_TURNS=3`), adversarial streak escalation (`MAX_ADVERSARIAL_STREAK=3` → `human_request_detected`), idempotency (`src/idempotency.py`), concurrent-call rejection (Temporal `workflow_id` collision), etc. |

Per `CLAUDE.md` §5 ("the spec wins on required behavior; the phase docs win on which
phase"), this is not a scope cut — the 9 blocked items stay on the checklist, get a real
scripted-test entry each, and that test is marked `pytest.mark.xfail(reason="blocked on
Phase 5 risk/privacy domain", strict=True)` rather than silently omitted. `strict=True`
means the test **fails the suite** the day Phase 5 actually ships that domain and someone
forgets to unmark it — turning "we'll remember to come back to this" into a mechanically
enforced TODO, the same discipline `CLAUDE.md` §4 asks for everywhere else.

### 0.4 The defect log is a DB-backed domain (dashboard-observable), not a checked-in file — and it is explicitly not audit-insert-only

`src/audit/`'s `AuditEvent` is insert-only by design (`CLAUDE.md` §2.5, enforced 3 layers
deep per `backend-explorer`: service only exposes `record_event()`, ORM
`before_update`/`before_delete` listeners block mutation, DB role has no `UPDATE`/`DELETE`
grant) — because it is a **runtime call audit trail**, keyed by `call_id`/`correlation_id`.
A Phase 4 defect entry is the opposite kind of fact: it's dev-process QA metadata with no
`call_id`, and it has to move through real status transitions (`OPEN` → `FIX_APPLIED` →
`COMPILED`) and have its `occurrence_count` incremented — exactly the "soft-delete/
status-transition pattern" `CLAUDE.md` §2.5 describes for non-audit tables (`Complaint`,
`Customer`). `src/qa/` is therefore an ordinary mutable domain package, following the same
shape as `complaints/` — this is a deliberate contrast with `audit/`, not an oversight.

It's DB-backed (not a `qa/defect_log.yaml` file some team member edits by hand) because
`CLAUDE.md`'s whole architecture already gives this project a reviewable, ops-dashboard-
observable path for exactly this shape of data (Shape A, §1) — during an active hardening
session, whoever is running journeys needs to log a defect, see it counted, and see whether
it's been compiled, live, the same way they already watch `ComplaintSlaTimeline` or
`EscalationQueue`. A git-diff-reviewed YAML file would be reviewable after the fact, but not
usable *during* a hardening session the way the rest of this system's ops surface already is.

### 0.5 The two-strike rule is judged by a human, computed by the service — the CI gate only checks the paperwork got done

Whether two defects are "the same shape" is a judgment call spec §35/the phase file leaves
to whoever is running hardening — the system cannot and should not try to auto-detect that
semantically. What the system *can* enforce mechanically (per `CLAUDE.md`'s "if you can't
point to the mechanism that enforces it, it isn't actually enforced yet") is the paperwork
the phase file's rule requires once a human has made that judgment: **an entry whose
`occurrence_count` reaches 2 must carry a `compiled_artifact_ref` before it can be marked
`COMPILED`, and the exit criteria require zero entries stuck at `occurrence_count >= 2` with
`status != COMPILED`.** `qa/service.py::record_occurrence()` computes and stores a
`compilation_required: bool` on read; a new CI-adjacent script (§6) fails a run if any
entry has `compilation_required=True` and `status != "COMPILED"`.

### 0.6 The scripted-conversation suite reports its own results back into `qa/` — closing the loop without a human re-typing pass/fail

Per §0.4's reasoning, the defect log needs to be reviewable on the dashboard, but manually
re-entering "did Demo 3 pass under angry-customer injection today" after every regression
run would be exactly the kind of untracked, non-mechanical state `CLAUDE.md` warns against.
A small `pytest` `conftest.py` hook in the new `tests/scripted_conversations/` package posts
each parametrized test's outcome to `POST /qa/journey-runs` after the run (best-effort, not
required for the test to pass/fail — a dashboard-reporting failure must never fail the
actual regression test). This is the same "direct activity-function call, no workflow
guarantee, acceptable for non-customer-impacting telemetry" shape `phase-3-backend-spec.md`
§0.4 already established for `record_audit_event` — the reporting hook is dev-tooling
telemetry, not a customer-impacting write, so `src/idempotency.py` does not apply to it
(per `CLAUDE.md` §4, that rule scopes to `actions/`, `complaints/`, `verification/`,
`privacy/` — none of which this touches).

### 0.7 Adversarial-resistance re-run against a paid LLM is a manual, opt-in job — never part of the default $0 CI matrix

`IMPLEMENTATION_PLAN.md`'s stack table flags this precisely: the demo's zero-cost
`LLM_PROVIDER` (Gemini/Groq free tier) is "measurably weaker... at holding this line
[resisting jailbreak/system-override phrasing] than Claude," and says Phase 4/5 hardening
"should be re-run against Claude before any real deployment decision." That re-run costs
real money per call and must never silently become part of the per-commit CI job (which
already runs against a live Temporal+Postgres+Redis service-container matrix at zero
marginal cost). It is a separate, manually-dispatched job (§6.3), gated by an
`ANTHROPIC_API_KEY` secret being present, run deliberately before phase sign-off — not on
every push.

### 0.8 No new idempotency boundary, no new kill-switch path

This phase adds no new outbound-dial or customer-impacting-write code path — every write
`qa/` performs is dev-process metadata about *past* call attempts, never a decision that
originates or continues a call. `Depends(require_outbound_enabled)` and
`src/idempotency.py` are therefore both correctly absent from `qa/router.py` — noting this
explicitly (per the discipline `phase-3-backend-spec.md` §0.4/§0.6 already established of
stating what does *not* apply and why) rather than leaving a reviewer to wonder if it was
forgotten.

---

## 1. Folder structure — the Phase 3 → Phase 4 diff

```
backend/
├── src/
│   └── qa/                             # NEW — dev-process governance, not a call-center domain
│       ├── router.py                   # /qa/defect-log, /qa/journey-runs, /qa/governance-summary
│       ├── schemas.py                  # DefectLogEntryCreate/Read/Update, JourneyRunCreate/Read
│       ├── models.py                   # DefectLogEntry, JourneyRunResult
│       ├── service.py                  # record_occurrence(), update_status(), record_journey_run(),
│       │                                #   governance_summary()
│       ├── constants.py                # DemoJourneyId, AdversarialScenarioId, DefectStatus,
│       │                                #   CompiledArtifactType
│       ├── dependencies.py             # valid_defect_log_entry
│       └── exceptions.py
├── scripts/
│   ├── seed_demo_data.py               # MODIFIED — seeds a Ramadan window + one BLACKOUT date (§5.3)
│   └── ci/
│       └── check_defect_log_two_strike.py   # NEW — 5th gate script (§6.2), NOT in the default per-PR job
├── tests/
│   └── scripted_conversations/         # NEW
│       ├── conftest.py                 # journey-run reporting hook (§0.6), scenario-loading fixtures
│       ├── journeys/                   # one file per Demo 1–9, each the cooperative "happy path" script
│       │   ├── test_demo_1_successful_status_update.py
│       │   ├── test_demo_2_customer_busy.py
│       │   ├── test_demo_3_wrong_person.py
│       │   ├── test_demo_4_authentication_failure.py
│       │   ├── test_demo_5_document_status_dispute.py
│       │   ├── test_demo_6_delayed_claim_dissatisfied.py
│       │   ├── test_demo_7_multi_turn_questions.py
│       │   ├── test_demo_8_human_complaint_escalation.py
│       │   └── test_demo_9_no_answer.py
│       ├── adversarial/                # one file per canonical adversarial scenario (§2 table),
│       │   │                            #   each parametrized across the journeys it applies to
│       │   ├── test_barge_in.py
│       │   ├── test_silence_unclear.py
│       │   ├── test_angry_distressed.py
│       │   ├── test_code_switching_en_ar.py
│       │   ├── test_jailbreak_system_override.py
│       │   ├── test_prompt_extraction_attempt.py
│       │   ├── test_auth_refused_and_incorrect.py
│       │   ├── test_contradictory_statements.py
│       │   ├── test_system_data_unavailable.py
│       │   ├── test_vendor_timeout_mid_call.py       # LLM/STT/TTS timeout, parametrized by adapter
│       │   ├── test_telephony_failure_mid_call.py
│       │   ├── test_dtmf_fallback_trigger.py
│       │   ├── test_unprompted_pii_disclosure.py
│       │   ├── test_invalid_unauthorized_cli.py
│       │   ├── test_concurrent_call_collision.py
│       │   ├── test_contact_window_blackout.py
│       │   ├── test_answer_seizure_timeout.py
│       │   ├── test_backend_timeout_post_auth.py
│       │   ├── test_idempotency_replay.py            # both "response lost" and "same-key retry" cases
│       │   ├── test_otp_abuse_lifecycle.py
│       │   ├── test_worker_restart_mid_session.py
│       │   └── test_call_drop_pre_post_auth.py
│       └── blocked_phase5/             # xfail(strict=True) placeholders, per §0.3
│           ├── test_dsar_request.py
│           ├── test_minor_answered.py
│           ├── test_communication_suppression.py
│           ├── test_recording_consent_refused.py
│           ├── test_fraud_signal_covert_routing.py
│           ├── test_vulnerable_customer_disclosure.py
│           ├── test_legal_sensitivity_evidence_hold.py
│           └── test_sim_swap_risk_signal.py
├── requirements/
│   └── dev.txt                         # unchanged — no new library needed (see §0.2)
└── migrations/
    └── versions/
        └── 2026-08-29_add_qa_domain_tables.py   # NEW — DefectLogEntry, JourneyRunResult
```

`src/main.py` gains one line: `app.include_router(qa_router, prefix="/qa", tags=["qa"])`,
the same pattern every other domain already follows (`CLAUDE.md` §2.2).

---

## 2. Canonical adversarial-scenario IDs — deduping the phase file's checklist

`phases/phase-4-demo-hardening.md` lines 35–70 list 34 raw bullets, but several are the
same underlying mechanism described twice in different words (confirmed against
`backend-explorer`'s findings on what code each maps to). Collapsing them into stable,
enum-backed IDs — instead of writing 34 near-duplicate test files, several of which would
silently test the exact same code path twice under slightly different names — is a
correctness fix for the checklist itself, not just a code-organization choice:

| Raw checklist wording | Canonical `AdversarialScenarioId` | Underlying mechanism |
|---|---|---|
| "STT uncertainty / low confidence" + "Persistent low STT confidence → accessibility/DTMF fallback" + "Three consecutive low-STT turns → DTMF fallback" | `DTMF_FALLBACK_TRIGGERED` | `voice/dtmf.py`, `MAX_CONSECUTIVE_LOW_STT_TURNS=3` |
| "LLM timeout mid-call" + "LLM/STT/TTS timeout mid-call" | `VENDOR_TIMEOUT_MID_CALL` (parametrized: `llm`\|`stt`\|`tts`) | `ErrorFrame` handling in `_ConversationTapProcessor` → `RuntimeFailureEvent` |
| "Backend action committed but response lost (idempotency replay)" + "Repeated action retry with the same idempotency key" | `IDEMPOTENCY_REPLAY` (two cases in one test file) | `src/idempotency.py` |
| "Incorrect authentication (both attempts)" + "Customer refuses authentication" | kept as **two** distinct IDs (`AUTH_INCORRECT_BOTH_ATTEMPTS`, `AUTH_REFUSED`) — different code paths (lockout vs. refusal), not a duplicate | `verification/service.py` |

Every other raw bullet maps 1:1 to its own `AdversarialScenarioId` member. The full,
authoritative list lives in `src/qa/constants.py` as a Python `StrEnum` — 28 members after
dedup (9 blocked-on-Phase-5 members marked via a parallel `PHASE_5_BLOCKED` frozenset,
mirroring `calls/constants.py::FUTURE_GLOBAL_INTERRUPTS`'s existing convention exactly) —
and every test file under `tests/scripted_conversations/` references a member of this enum
by name rather than a free-text string, so a future rename is a one-place edit.

```python
# src/qa/constants.py
from enum import StrEnum

class DemoJourneyId(StrEnum):
    DEMO_1_SUCCESSFUL_STATUS_UPDATE = "DEMO_1_SUCCESSFUL_STATUS_UPDATE"
    DEMO_2_CUSTOMER_BUSY = "DEMO_2_CUSTOMER_BUSY"
    DEMO_3_WRONG_PERSON = "DEMO_3_WRONG_PERSON"
    DEMO_4_AUTHENTICATION_FAILURE = "DEMO_4_AUTHENTICATION_FAILURE"
    DEMO_5_DOCUMENT_STATUS_DISPUTE = "DEMO_5_DOCUMENT_STATUS_DISPUTE"
    DEMO_6_DELAYED_CLAIM_DISSATISFIED_CUSTOMER = "DEMO_6_DELAYED_CLAIM_DISSATISFIED_CUSTOMER"
    DEMO_7_MULTI_TURN_QUESTIONS = "DEMO_7_MULTI_TURN_QUESTIONS"
    DEMO_8_HUMAN_COMPLAINT_ESCALATION = "DEMO_8_HUMAN_COMPLAINT_ESCALATION"
    DEMO_9_NO_ANSWER = "DEMO_9_NO_ANSWER"

class AdversarialScenarioId(StrEnum):
    BARGE_IN = "BARGE_IN"
    SILENCE_UNCLEAR = "SILENCE_UNCLEAR"
    ANGRY_DISTRESSED = "ANGRY_DISTRESSED"
    CODE_SWITCHING_EN_AR = "CODE_SWITCHING_EN_AR"
    WRONG_PERSON = "WRONG_PERSON"
    AUTH_REFUSED = "AUTH_REFUSED"
    AUTH_INCORRECT_BOTH_ATTEMPTS = "AUTH_INCORRECT_BOTH_ATTEMPTS"
    CONTRADICTORY_STATEMENTS = "CONTRADICTORY_STATEMENTS"
    SYSTEM_DATA_UNAVAILABLE = "SYSTEM_DATA_UNAVAILABLE"
    TELEPHONY_FAILURE_MID_CALL = "TELEPHONY_FAILURE_MID_CALL"
    VENDOR_TIMEOUT_MID_CALL = "VENDOR_TIMEOUT_MID_CALL"
    JAILBREAK_SYSTEM_OVERRIDE = "JAILBREAK_SYSTEM_OVERRIDE"
    PROMPT_EXTRACTION_ATTEMPT = "PROMPT_EXTRACTION_ATTEMPT"
    UNPROMPTED_PII_DISCLOSURE = "UNPROMPTED_PII_DISCLOSURE"
    DTMF_FALLBACK_TRIGGERED = "DTMF_FALLBACK_TRIGGERED"
    INVALID_UNAUTHORIZED_CLI = "INVALID_UNAUTHORIZED_CLI"
    CONCURRENT_CALL_COLLISION = "CONCURRENT_CALL_COLLISION"
    CONTACT_WINDOW_BLACKOUT = "CONTACT_WINDOW_BLACKOUT"
    ANSWER_SEIZURE_TIMEOUT = "ANSWER_SEIZURE_TIMEOUT"
    BACKEND_TIMEOUT_POST_AUTH = "BACKEND_TIMEOUT_POST_AUTH"
    IDEMPOTENCY_REPLAY = "IDEMPOTENCY_REPLAY"
    OTP_ABUSE_LIFECYCLE = "OTP_ABUSE_LIFECYCLE"
    WORKER_RESTART_MID_SESSION = "WORKER_RESTART_MID_SESSION"
    CALL_DROP_PRE_POST_AUTH = "CALL_DROP_PRE_POST_AUTH"
    # Phase 5-blocked (see §0.3) — present so the checklist is complete, not silently dropped
    DSAR_REQUEST = "DSAR_REQUEST"
    MINOR_ANSWERED = "MINOR_ANSWERED"
    COMMUNICATION_SUPPRESSION_REQUEST = "COMMUNICATION_SUPPRESSION_REQUEST"
    RECORDING_CONSENT_REFUSED = "RECORDING_CONSENT_REFUSED"
    FRAUD_SIGNAL_COVERT_ROUTING = "FRAUD_SIGNAL_COVERT_ROUTING"
    VULNERABLE_CUSTOMER_DISCLOSURE = "VULNERABLE_CUSTOMER_DISCLOSURE"
    LEGAL_SENSITIVITY_EVIDENCE_HOLD = "LEGAL_SENSITIVITY_EVIDENCE_HOLD"
    SIM_SWAP_RISK_SIGNAL = "SIM_SWAP_RISK_SIGNAL"

PHASE_5_BLOCKED_SCENARIOS = frozenset({
    AdversarialScenarioId.DSAR_REQUEST,
    AdversarialScenarioId.MINOR_ANSWERED,
    AdversarialScenarioId.COMMUNICATION_SUPPRESSION_REQUEST,
    AdversarialScenarioId.RECORDING_CONSENT_REFUSED,
    AdversarialScenarioId.FRAUD_SIGNAL_COVERT_ROUTING,
    AdversarialScenarioId.VULNERABLE_CUSTOMER_DISCLOSURE,
    AdversarialScenarioId.LEGAL_SENSITIVITY_EVIDENCE_HOLD,
    AdversarialScenarioId.SIM_SWAP_RISK_SIGNAL,
})

class DefectStatus(StrEnum):
    OPEN = "OPEN"
    FIX_APPLIED = "FIX_APPLIED"
    COMPILED = "COMPILED"
    WONT_FIX = "WONT_FIX"

class CompiledArtifactType(StrEnum):
    REGRESSION_TEST = "REGRESSION_TEST"          # e.g. new scripted_conversations test
    GUARD_PHRASE_RULE = "GUARD_PHRASE_RULE"       # new entry in voice/guard.py's phrase corpus
    TOOL_ALLOWLIST_RULE = "TOOL_ALLOWLIST_RULE"   # new voice/tools.py or CI allowlist check
    NON_NEGOTIABLE_RULE = "NON_NEGOTIABLE_RULE"   # a genuinely new §36-equivalent rule
```

---

## 3. Data model

```python
# src/qa/models.py
from datetime import datetime
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.models import Base

class DefectLogEntry(Base):
    __tablename__ = "qa_defect_log_entry"
    id: Mapped[str] = mapped_column(primary_key=True)
    title: Mapped[str]
    defect_shape_key: Mapped[str]              # human-assigned slug used to match recurrences
    demo_journey_id: Mapped[str | None]        # DemoJourneyId, nullable (cross-cutting defects)
    adversarial_scenario_id: Mapped[str | None]  # AdversarialScenarioId, nullable (cooperative-path defects)
    language: Mapped[str] = mapped_column(default="EN")  # "EN" | "AR" | "CODE_SWITCH"
    severity: Mapped[str] = mapped_column(default="MEDIUM")  # "LOW" | "MEDIUM" | "HIGH"
    status: Mapped[str] = mapped_column(default="OPEN")      # DefectStatus
    occurrence_count: Mapped[int] = mapped_column(default=1)
    compiled_artifact_type: Mapped[str | None]  # CompiledArtifactType
    compiled_artifact_ref: Mapped[str | None]   # e.g. "tests/scripted_conversations/adversarial/test_x.py::test_y"
    first_seen_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]
    notes: Mapped[str | None]

class JourneyRunResult(Base):
    __tablename__ = "qa_journey_run_result"
    id: Mapped[str] = mapped_column(primary_key=True)
    demo_journey_id: Mapped[str]                # DemoJourneyId
    adversarial_scenario_id: Mapped[str | None]  # null = cooperative/happy-path run
    passed: Mapped[bool]
    run_at: Mapped[datetime]
    defect_log_entry_id: Mapped[str | None] = mapped_column(ForeignKey("qa_defect_log_entry.id"))
    test_node_id: Mapped[str]                    # pytest's own node id, for traceability
```

Both tables are plain mutable rows (§0.4) — no insert-only enforcement, no idempotency
decorator. Migration `2026-08-29_add_qa_domain_tables.py` creates both tables plus the
naming-convention-derived FK constraint (`qa_journey_run_result_defect_log_entry_id_fkey`,
per `CLAUDE.md` §2.1's `POSTGRES_INDEXES_NAMING_CONVENTION`).

### 3.1 Pydantic schemas (three-schema convention, `CLAUDE.md` §2.4)

```python
# src/qa/schemas.py
from datetime import datetime
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field

class DefectLogEntryCreate(BaseModel):
    title: Annotated[str, Field(max_length=200)]
    defect_shape_key: Annotated[str, Field(max_length=100)]
    demo_journey_id: str | None = None
    adversarial_scenario_id: str | None = None
    language: Annotated[str, Field(pattern="^(EN|AR|CODE_SWITCH)$")] = "EN"
    severity: Annotated[str, Field(pattern="^(LOW|MEDIUM|HIGH)$")] = "MEDIUM"
    notes: Annotated[str | None, Field(max_length=2000)] = None

class DefectLogEntryRead(DefectLogEntryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: str
    occurrence_count: int
    compiled_artifact_type: str | None
    compiled_artifact_ref: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    compilation_required: bool   # computed: occurrence_count >= 2 and status != "COMPILED"

class DefectLogEntryUpdate(BaseModel):
    status: Annotated[str | None, Field(pattern="^(OPEN|FIX_APPLIED|COMPILED|WONT_FIX)$")] = None
    compiled_artifact_type: Annotated[str | None, Field(max_length=32)] = None
    compiled_artifact_ref: Annotated[str | None, Field(max_length=300)] = None
    notes: Annotated[str | None, Field(max_length=2000)] = None

class DefectOccurrenceCreate(BaseModel):
    """Records a repeat sighting of an existing defect_shape_key — increments occurrence_count."""
    demo_journey_id: str | None = None
    adversarial_scenario_id: str | None = None
    notes: Annotated[str | None, Field(max_length=2000)] = None

class JourneyRunCreate(BaseModel):
    demo_journey_id: str
    adversarial_scenario_id: str | None = None
    passed: bool
    test_node_id: Annotated[str, Field(max_length=300)]
    defect_log_entry_id: str | None = None

class JourneyRunRead(JourneyRunCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    run_at: datetime

class GovernanceSummary(BaseModel):
    total_defects: int
    open_defects: int
    compilation_required_count: int   # occurrence_count >= 2 and not COMPILED — the CI-gated number
    journeys_passing: int              # of 9, latest run per journey (cooperative baseline) is `passed=True`
    journeys_total: int = 9
```

`compilation_required`, like `ComplaintRead`'s SLA fields (`CLAUDE.md` §2.4), is never
client-settable — it's computed in `service.py` from `occurrence_count`/`status` at read
time, never stored redundantly, so it can never drift out of sync with the two fields it's
derived from.

---

## 4. API routes

| Method | Path | Purpose | Response model |
|---|---|---|---|
| `POST` | `/qa/defect-log` | Log a new defect (first occurrence) | `DefectLogEntryRead` |
| `GET` | `/qa/defect-log` | List defects, paginated (`src/pagination.py`), filterable by `status`, `demo_journey_id` | `Page[DefectLogEntryRead]` |
| `GET` | `/qa/defect-log/{id}` | Fetch one | `DefectLogEntryRead` |
| `PATCH` | `/qa/defect-log/{id}` | Update status / attach compiled artifact | `DefectLogEntryRead` |
| `POST` | `/qa/defect-log/{shape_key}/occurrences` | Record a repeat sighting — increments `occurrence_count`, bumps `last_seen_at` | `DefectLogEntryRead` |
| `POST` | `/qa/journey-runs` | Record one scripted-test outcome (called by the pytest reporting hook, §0.6) | `JourneyRunRead` |
| `GET` | `/qa/journey-runs` | List recent runs, filterable by `demo_journey_id` | `Page[JourneyRunRead]` |
| `GET` | `/qa/governance-summary` | Dashboard header numbers (§3.1) | `GovernanceSummary` |

Routers stay thin per `CLAUDE.md` §2.2 — `valid_defect_log_entry` (a `Depends()`, matching
`calls/dependencies.py::valid_call_session`'s exact shape) handles the repeated "fetch or
404" for `{id}`-scoped routes; `POST /qa/defect-log/{shape_key}/occurrences` looks up by
`defect_shape_key` (not `id`) precisely because that's the field a hardening session actually
has in hand when they see the same defect shape again — they don't necessarily remember the
UUID from the first sighting.

```python
# src/qa/service.py — the two functions with real logic
async def record_occurrence(db, shape_key: str, payload: DefectOccurrenceCreate) -> DefectLogEntry:
    entry = await _get_by_shape_key(db, shape_key)
    if entry is None:
        raise DefectShapeKeyNotFound(shape_key)
    async with db.begin():
        entry.occurrence_count += 1
        entry.last_seen_at = payload_now()
        if payload.notes:
            entry.notes = f"{entry.notes or ''}\n[occurrence {entry.occurrence_count}] {payload.notes}".strip()
    return entry

def compilation_required(entry: DefectLogEntry) -> bool:
    return entry.occurrence_count >= 2 and entry.status != DefectStatus.COMPILED
```

---

## 5. Making the blocked-but-testable checklist item actually testable: contact-window blackout data

`telephony/models.py::BusinessContactCalendar` and `telephony/service.py::
is_within_contact_window()` already exist and work — they just have no seeded rows, so
every date resolves `contact_allowed=True` by default (per `models.py`'s own docstring:
"real Ramadan/holiday data is a Phase 5 concern," which correctly scopes *production*
calendar data as Phase 5, but leaves this phase with literally nothing to test the
mechanism against). Phase 4 needs the mechanism to be exercisable now, without waiting on
Phase 5's real UAE public-holiday data feed — so this phase adds a small, clearly
synthetic seed addition, not production calendar data:

```python
# scripts/seed_demo_data.py — addition
DEMO_CALENDAR_ROWS = [
    # synthetic, demo-only — NOT real UAE Ramadan/holiday dates, see phase-5 for that feed
    {"calendar_date": "2026-09-05", "calendar_type": "RAMADAN", "contact_allowed": False},
    {"calendar_date": "2026-09-06", "calendar_type": "BLACKOUT", "contact_allowed": False},
]
```

`test_contact_window_blackout.py` asserts a call attempt scheduled against `2026-09-06`
is rejected by `is_within_contact_window()` before any dial happens — closing the one
checklist item that had a mechanism but no data, while leaving the 8 items with no
mechanism at all correctly marked `blocked_phase5/` (§0.3).

---

## 6. CI / governance gates

### 6.1 Existing `backend-ci.yml` job — unchanged, plus the new suite runs alongside the existing `pytest tests -v --cov=src`

`tests/scripted_conversations/` is a subpackage of `tests/`, so it's picked up by the
existing `pytest tests` invocation with no workflow-file change. The existing four gate
scripts (`check_tool_allowlist.py`, `check_disposition_action_codes.py`,
`check_no_raw_prompt_concat.py`, `check_transcript_redaction.py`) run exactly as before —
this phase adds test coverage that exercises those same allow-listed tools/dispositions
under adversarial pressure, it doesn't change what the gates check.

### 6.2 `scripts/ci/check_defect_log_two_strike.py` — a separate governance job, not part of the default per-PR matrix

Per §0.4/§0.5's reasoning: the defect log's data lives in the persistent hardening/staging
Postgres (where a human actually ran the journeys and logged defects through the dashboard),
not the fresh, empty ephemeral Postgres the standard `backend-ci.yml` job spins up per PR.
Querying an empty ephemeral DB for this check would always trivially pass and mean nothing.
This script is therefore wired as its own `.github/workflows/phase4-governance-check.yml`,
`workflow_dispatch`-triggered (run deliberately, e.g. before signing off the phase — not on
every push), pointed at the staging `DATABASE_URL` via a repo secret:

```python
# scripts/ci/check_defect_log_two_strike.py
"""Fails if any defect has recurred twice without a compiled permanent check — the
mechanical enforcement of phases/phase-4-demo-hardening.md's two-strike rule."""
async def main() -> int:
    async with SessionLocal() as db:
        entries = await qa_service.list_all(db)
    blockers = [e for e in entries if qa_service.compilation_required(e)]
    if blockers:
        for e in blockers:
            print(f"UNCOMPILED (seen {e.occurrence_count}x): {e.title} [{e.id}]")
        return 1
    print(f"OK — {len(entries)} defects reviewed, none pending compilation.")
    return 0
```

### 6.3 Claude adversarial-resistance re-run — manual, opt-in, cost-aware (per §0.7)

A second `workflow_dispatch` job, `phase4-claude-adversarial-rerun.yml`, sets
`VOICE_LLM_PROVIDER=claude` as an environment override and re-runs only
`tests/scripted_conversations/adversarial/test_jailbreak_system_override.py` and
`test_prompt_extraction_attempt.py` (the two scenarios `IMPLEMENTATION_PLAN.md` specifically
calls out) against the real Anthropic API. Guarded by `if: ${{ secrets.ANTHROPIC_API_KEY !=
'' }}` so it's a no-op (not a failure) in any fork/environment that hasn't provisioned the
key — this keeps the default $0-cost CI promise (`IMPLEMENTATION_PLAN.md` §1) intact while
making the paid re-run a one-click action when it's actually time to do it.

---

## 7. Exit-criteria mapping

| Phase file exit criterion | Backend mechanism |
|---|---|
| "All 9 demo journeys pass repeatedly under the full adversarial checklist" | `tests/scripted_conversations/journeys/*` × `adversarial/*` parametrization, reported into `qa_journey_run_result` via §0.6's hook |
| "Every defect found twice has a corresponding permanent automated check" | `qa/service.py::compilation_required()` + `scripts/ci/check_defect_log_two_strike.py` (§6.2) |
| "The defect log itself exists and is reviewable" | `GET /qa/defect-log` (paginated), `GET /qa/governance-summary` — consumed by the frontend spec's dashboard page |

---

## 8. Deferred / explicitly out of scope

- A real fake/test STT adapter for true end-to-end audio-in pipeline testing (§0.2) —
  tracked as a follow-up, not required by spec §35's Phase 4 description.
- The 8 `blocked_phase5/` scenarios (§0.3) — cannot be un-blocked without Phase 5's
  `src/risk/`, `PrivacyRequest`, `RecordingConsent`, `CommunicationSuppression` domains
  existing first. `strict=True` `xfail` markers make this mechanically visible the moment
  Phase 5 ships and someone forgets to update these tests.
- Real UAE Ramadan/public-holiday calendar data (§5) — only synthetic demo rows are added
  this phase; the real feed is Phase 5's `BusinessContactCalendar` production data-source
  task.
- Wiring `ADVERSARIAL_INPUT_DETECTED` (and the other 8 `FUTURE_GLOBAL_INTERRUPTS` members)
  as first-class workflow-consumed signals — today the streak-based escalation to
  `human_request_detected` after `MAX_ADVERSARIAL_STREAK=3` already provides a real,
  testable containment mechanism; promoting the raw signal itself to a distinct workflow
  interrupt is a `calls/` design decision `phase-3-backend-spec.md`'s successor phase should
  make deliberately, not a side effect of adding tests here.

---
**Previous:** [Phase 3 — Backend Spec](./phase-3-backend-spec.md)
**Companion:** [Phase 4 — Frontend Spec](./phase-4-frontend-spec.md)
