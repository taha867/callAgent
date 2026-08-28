# Phase 1 — Backend Engineering Spec (Deterministic Core)

**Derived from:** `Insurance_Outbound_AI_Call_Center_Motor_MVP_Developer_Spec_v1_3.md` §2.3,
§3/§3.1, §4/§4.1, §6, §8.1–§8.6, §9, §10, §11–§14, §15, §18/§18.1, §19/§19.1/§19.2, §20, §22,
§23, §24, §25, §26, §27, §32, §35 Phase 1, §36, §38 · `phases/phase-1-deterministic-core.md` ·
`IMPLEMENTATION_PLAN.md` §0–§2 · `CLAUDE.md` §1–§2 (backend conventions) ·
`.claude/specs/phase-0-backend-spec.md` (this phase's actual starting code state)

**Purpose of this document:** `phases/phase-1-deterministic-core.md` gives Phase 1 a
10-item task list and a 15-branch exit criterion; it does not say which files those tasks
become, how `calls/` and `campaigns/` divide the Master Call State Machine from the retry
scheduler, or how a phase with no real voice component proves a "conversation" happened.
This document is that missing layer, written against the **actual Phase 0 code already in
`backend/src/`** (read in full before drafting this spec) rather than against
`phase-0-backend-spec.md`'s design intent — every stub this phase replaces
(`calls/workflows.py`'s `CallSessionWorkflow`, `calls/constants.py`'s `CallState`,
`voice/tools.py`'s `dispatch_tool_call`, `worker.py`'s empty registries) is named by its
real current shape, not re-derived from scratch.

Phase 1 is explicitly the largest, highest-stakes phase in this repo (see the phase file's
own Notes section: "a bug here — an auth bypass, a non-idempotent write, a disposition code
that's wrong — ships into every later phase invisibly"). This spec is correspondingly the
most detailed of the series so far.

---

## 0. Design decisions (read this before implementing)

`phases/phase-1-deterministic-core.md`'s 10 tasks and spec §26's "suggested" entity list
leave several architectural questions genuinely open. Resolving them now, once, so no two
files in this phase disagree with each other.

### 0.1 Two workflows, not one: `CallSessionWorkflow` (per attempt) vs. `RetrySchedulerWorkflow` (per job)

`CLAUDE.md` §2.1 assigns the Master Call State Machine to `calls/workflows.py`
(`CallSessionWorkflow`, "one per call attempt, workflow ID derived from `customer_id`") and
the no-answer/retry scheduler to `campaigns/workflows.py` (`RetrySchedulerWorkflow`, "keyed
by `call_job_id`"). The phase task list (tasks 2 and 9) names both but never states how they
call each other. Resolution:

- **`RetrySchedulerWorkflow`** (`campaigns/workflows.py`, `workflow_id = f"retry-{call_job_id}"`)
  is the **outer, long-lived** workflow. It owns spec §6's attempt-1/2/3 timing, §6.2's
  retry-variation bookkeeping, and §6.9's critical-status override. It does not talk to the
  customer — it decides *when* to attempt and delegates the actual dial+conversation to a
  child workflow.
- **`CallSessionWorkflow`** (`calls/workflows.py`, `workflow_id = f"call-session-{customer_id}"`)
  is the **inner, single-attempt** workflow. `RetrySchedulerWorkflow` starts one as a
  **child workflow** (`workflow.start_child_workflow`, not a plain activity call — see §0.2
  for why the child relationship matters) for every attempt, waits for its result, and uses
  that result's `disposition_code` to decide whether/when to schedule the next attempt.
- A call placed outside any campaign (a one-off ad hoc call, if ever needed) can start
  `CallSessionWorkflow` directly with the same customer-keyed ID — the lock and execution
  timeout behave identically either way.

```python
# campaigns/workflows.py — the parent's per-attempt step, sketch
handle = await workflow.start_child_workflow(
    CallSessionWorkflow.run,
    CallSessionInput(call_id=attempt_id, customer_id=job.customer_id, claim_id=job.claim_id),
    id=f"call-session-{job.customer_id}",
    parent_close_policy=ParentClosePolicy.ABANDON,  # see 0.2 — a live call must not be torn
)                                                     # down if the scheduler itself exits
try:
    result = await handle
except WorkflowAlreadyStartedError:
    # another AI or human session already holds this customer's lock — spec §4.1
    result = CallSessionOutput(call_id=attempt_id, disposition_code=DispositionCode.CONCURRENT_CALL_CONFLICT)
```

### 0.2 The distributed voice lock is Temporal's workflow-ID uniqueness — there is no `distributed_voice_locks` table

`CLAUDE.md`'s `telephony/` package bullet lists `DistributedVoiceLock` as a model name, but
its Architecture Overview section and its Temporal Workflows section (§2.6) both say the
opposite, twice, in more detail: *"a second workflow for the same customer is rejected by
Temporal itself — this rejection **is** the distributed voice lock ... not a separate lock
table to maintain."* The repeated, more specific statement wins over the one-line package
bullet (`CLAUDE.md` §5's own tie-break rule: this file governs code shape, and where it
disagrees with itself the fuller explanation is the real intent). Concretely:

- No `telephony.DistributedVoiceLock` SQLAlchemy model exists. `telephony/models.py` in
  this phase contains only `TelephonyCliConfiguration` and `BusinessContactCalendar`.
- The lock **is acquired** by `workflow.start_child_workflow(CallSessionWorkflow.run, id=f"call-session-{customer_id}", id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE)`
  — Temporal's default `ALLOW_DUPLICATE` reuse policy permits starting a new execution once
  the previous one with that ID has **closed**, and raises
  `WorkflowAlreadyStartedError` if one is still **running**. That exception, caught at the
  call site above, *is* `CONCURRENT_CALL_CONFLICT` — no polling, no row to clean up.
- Spec §4.1's "bounded TTL and crash-safe release" requirement — the real reason a hand-rolled
  lock table needs a reconciliation job — is satisfied natively by setting
  `execution_timeout=timedelta(seconds=settings.MAX_CALL_SESSION_SECONDS)` (default 900s) on
  `CallSessionWorkflow`. If the workflow (or the process running its worker) crashes or
  hangs, Temporal force-closes the execution once the timeout elapses, which frees the
  customer-keyed ID for the next attempt automatically. No separate TTL/reconciliation code
  is written in this phase.
- `spec §26`'s `distributed_voice_locks` entity is therefore **not implemented as a table**.
  This is documented here, not silently dropped, because it is the one place this spec
  deliberately does *less* than the spec's own suggested schema — on the grounds that
  `CLAUDE.md`'s own more detailed guidance says the mechanism it names is better.

### 0.3 `CallAttempt` (dial outcome + disposition) vs. `CallSession` (live conversation state) — two tables, not one

Spec §26 lists `call_attempts` and `call_sessions` as separate entities but never says how
they differ; §6.10's "No-Answer Data Model" and §10.6.2's "Persisted Session State" turn out
to be two different shapes, which settles it:

- **`CallAttempt`** — one row per dial, created by the orchestrator *before* dialing,
  covering §6.10's fields (`attempt`, `attempted_at`, `result`, `next_attempt_at`,
  `voicemail_detected`, `sms_sent`, `attempts_remaining`) plus §23's structured outcome
  fields (`customer_reached`, `right_party`, `verified`, `verification_level`,
  `status_delivered`, `resolution`, `duration_seconds`, `disposition_code`, ...). This row
  exists even for `NO_ANSWER`/`VOICEMAIL`/`CONCURRENT_CALL_CONFLICT` attempts — it is the
  table `CallSessionWorkflow`'s final activity always writes to, successful or not.
- **`CallSession`** — created **only** when a `CallAttempt` reaches `HumanAnswered`,
  covering §10.6.2's recovery-state fields (`state`, `right_party_confirmed`,
  `verification_level`, `status_already_disclosed`, `pending_action`,
  `last_committed_event_id`). It is 1:0..1 with its owning `CallAttempt` and is what the
  Master Call State Machine actually mutates turn by turn.

`CallAttempt.disposition_code` is the column already anticipated by
`phase-0-backend-spec.md` decision 5 (the `Enum(..., native_enum=False)` pattern proven in
Phase 0 against `claims.MotorClaim.claim_stage`) — this phase is where it gets used for
real.

### 0.4 Phase 1's slice of spec §26 — what gets built now vs. deferred

The task list says "all entities from spec §26," but §26 also lists entities that belong to
features Phase 1's own exit criteria never exercises (fraud/vulnerability/legal-sensitivity
routing, DSAR, PII redaction, knowledge/FAQ, sentiment, transcripts). Building those tables
now would be exactly the "half-finished implementation" `CLAUDE.md` warns against — there is
no service that reads or writes them yet. Phase 1 builds the subset that the 15 branches in
`phases/phase-1-deterministic-core.md`'s exit criteria (mirroring spec §38's Developer
Definition of Done) actually require:

| §26 entity | Phase 1 | Where | Why |
|---|---|---|---|
| `customers` | exists (Phase 0) | `customers/models.py` | — |
| `customer_contact_preferences` | **build** | `customers/models.py` | language/channel preference feeds eligibility + status-engine language selection |
| `customer_auth_factors` | **build** | `customers/models.py` | Level 1 knowledge-factor verification (task 5) needs a place to read the approved answer from |
| `motor_policies` … `repair_garages` | exist (Phase 0) | `claims/models.py` | — |
| `claim_actions` | **build** | `actions/models.py` | task 7 |
| `complaints`, `complaint_sla_events` | **build** | `complaints/models.py` | task 7, §18.1 |
| `outbound_campaigns`, `call_jobs` | **build** | `campaigns/models.py` | task 4/9 |
| `call_attempts`, `call_sessions` | **build** | `calls/models.py` | task 1/2/8, see 0.3 |
| `verification_attempts`, `otp_challenges` | **build** | `verification/models.py` | task 5 |
| `callbacks`, `escalations` | **build** | `actions/models.py` | task 7 (`BUSY CUSTOMER → callback`, `HUMAN REQUEST → transfer/callback` branches) |
| `audit_events` | exists (Phase 0) | `audit/models.py` | — |
| `runtime_failure_events` | **build** | `audit/models.py` | task 10 — `CLAUDE.md`'s `audit/` bullet places `RuntimeFailureEvent` here, not in `calls/` |
| `idempotency_records` | exists (Phase 0) | `src/idempotency.py` | — |
| `telephony_cli_configurations`, `business_contact_calendars` | **build (stub data)** | `telephony/models.py` | task 4, explicitly "stub" per the task wording |
| `distributed_voice_locks` | **not built** | — | see 0.2 |
| `communication_suppressions` | deferred → Phase 2/5 | — | eligibility check (§0.6) hardcodes "not suppressed" for Phase 1; the customer-facing "stop calling me" *interrupt* needs live conversation understanding (Phase 2) and the suppression-scope policy work is Phase 5's |
| `knowledge_articles` | deferred → Phase 2/3 | — | Type A/B follow-up answering is exercised through the fake/text harness against claims data directly (§8 below); a FAQ knowledge base isn't needed to prove the `QUESTION → grounded answer` branch |
| `privacy_requests`, `recording_consents`, `pii_redaction_events` | deferred → Phase 5 | — | not in the 15-branch exit criteria; §7.1 disclosure/consent branching and §28's redaction pipeline need real transcript content (Phase 2) and dedicated hardening (Phase 5) |
| `security_events`, `accessibility_routing_events` | deferred → Phase 2/3/5 | — | need STT confidence signals / adversarial-input detection that don't exist without real voice |
| `call_events`, `call_transcripts`, `call_summaries`, `customer_intents`, `sentiment_events` | deferred → Phase 2/3 | — | populated from real conversation content; Phase 1's harness produces `AuditEvent` rows and the final `CallAttempt`/`CallSession` state, which is what the exit criteria says to verify against ("reading the `AuditEvent`/outcome-record rows, not eyeballing logs") |
| `fraud_routing_events`, `vulnerability_routing_events`, `legal_sensitivity_events`, `evidence_preservation_requests`, `legal_holds` | deferred → Phase 5 | — | `risk/` domain, spec §19A/§8.10/§28's legal-sensitivity section — none in the 15 branches |
| `dependency_health_events` | deferred → Phase 3 | — | dashboard-facing aggregate; `runtime_failure_events` (built now) is the per-incident record Phase 3 aggregates from |

### 0.5 The fake/text conversation harness: signals in, activities out

The phase's Goal is explicit: *"If this phase is done correctly, Phase 2 only has to
replace the stub input/output — none of this phase's decision logic changes when real voice
is wired in."* That constraint dictates the workflow's public shape, not just its internals.

`CallSessionWorkflow` exposes **Temporal signals** for every inbound conversational event
and **activities** for every deterministic, effectful step. Spec §3.1's global interrupts
are inherently signal-shaped already ("can occur from almost any active conversation
state") — this is not a new abstraction invented for testability, it is Temporal's native
fit for what the spec already describes.

```python
# calls/workflows.py — the signal surface Phase 2's voice/pipeline.py will call into,
# and the one this phase's fake/text harness calls instead.

@workflow.signal
async def customer_utterance(self, intent: CustomerIntentSignal) -> None: ...

@workflow.signal
async def otp_response(self, code: str) -> None: ...

@workflow.signal
async def human_request_detected(self) -> None: ...

@workflow.signal
async def call_dropped(self) -> None: ...

@workflow.query
def current_state(self) -> str: ...
```

`CustomerIntentSignal` is a small closed Pydantic model — `{"intent": "RIGHT_PARTY_CONFIRMED"}`,
`{"intent": "AUTH_ANSWER", "value": "1990"}`, `{"intent": "ASK_QUESTION", "topic": "GARAGE"}`,
`{"intent": "REQUEST_HUMAN"}`, `{"intent": "DISPUTE_DOCUMENT", "document_type": "POLICE_REPORT"}`,
etc. — one variant per branch the 15-item exit criteria requires. This is deliberately not
raw text: Phase 1 has no STT/LLM to turn speech into intent yet, so the harness supplies the
*already-classified* intent directly, matching exactly what Phase 2's real
`voice/pipeline.py` will extract and signal in once it exists — the workflow-side contract
does not change.

`tests/integration/test_phase1_e2e.py` is the harness: for each of the 15 branches, it
starts a `CallSessionWorkflow` (or `RetrySchedulerWorkflow` for the no-answer/retry branch),
sends a small scripted sequence of signals, awaits the result, and asserts
`disposition_code` plus the resulting `AuditEvent`/`CallAttempt` rows — never a real
audio/text conversation. This is the literal continuation of Phase 0's
`Phase0SmokeWorkflow` pattern (`phase-0-backend-spec.md` §4.3), scaled up to the real
`CallSessionWorkflow`.

### 0.6 Eligibility orchestration lives in `campaigns/service.py`, composed from other domains' reads

Spec §4's eligibility checklist spans customer suppression status, claim existence,
CLI/trunk validity, and the contact calendar — no single domain owns all of it. Per the
architecture diagram (node B "Outbound Orchestrator" feeding node Q
"Eligibility + CLI + Contact Window + Distributed Lock"), `campaigns/` is the orchestrator,
so `campaigns/service.py::check_call_eligibility()` is the one function that composes reads
from `customers/`, `claims/`, and `telephony/` and returns spec §4's example JSON shape. It
does not own new tables itself for this — it calls into the owning domains' `service.py`
modules. Per §0.4, the "no active suppression" check in this composition is a hardcoded
`True` for Phase 1 (no suppression table yet) — commented as such, not silently assumed.

### 0.7 OTP delivery is a swappable adapter, same pattern as `voice/adapters/*` — not a hardcoded stub

Spec §10.3.2 requires OTP to never be logged or stored in plaintext, but Phase 1 has no real
SMS/telephony vendor to deliver it through (that is Phase 6's paid-vendor swap). Rather than
special-casing "OTP delivery does nothing in dev," this phase applies the same adapter
pattern `CLAUDE.md` §2.7 already establishes for STT/TTS/LLM/telephony:

```python
# verification/adapters/otp_delivery/base.py
class OtpDeliveryAdapter(Protocol):
    async def send(self, *, phone_e164: str, code: str) -> None: ...
```

`verification/adapters/otp_delivery/log_only.py` implements it by writing only *that* an
OTP was sent (never the code) to the structured log, and — gated behind
`settings.ENVIRONMENT != "production"` — exposing the code through a dev-only Temporal query
(`CallSessionWorkflow.debug_last_otp_code`) that only `tests/integration/`'s harness calls.
This is the one deliberate seam that lets the fake/text harness complete an `OTP LIMIT →
lockout` and an `OTP → verified` branch without a real SMS vendor, while keeping spec §36
rule 18 ("never log passwords, PINs, CVV, OTPs...") intact in the actual delivery path.
`verification/config.py` names the active adapter (`OTP_DELIVERY_PROVIDER: str = "log_only"`),
same shape as `voice/config.py`'s `STT_PROVIDER`/`TTS_PROVIDER`.

### 0.8 Status engine is key-selection + disclosure redaction, not text generation

Task 6 says "template selection only, no free text generation yet" — this phase does not
write the English/Arabic message templates themselves (that is Phase 2's
`voice/pipeline.py`/prompt work). `claims/service.py::get_disclosable_status()` does two
things only:

1. Looks up `MotorClaim.approved_customer_message_key` (already a column, populated at
   claim-write time — Phase 1 does not compute it from `claim_stage` via a mapping table,
   since the field already exists 1:1 per claim in the Phase 0 schema).
2. Redacts fields the current `verification_level` doesn't clear — spec §13 Journey E
   ("higher authentication may be required for financial detail"): `settlement_amount` and
   `PAYMENT_INITIATED`'s amount are withheld below `L2`, matching spec §10.1's "not
   permitted at Level 0" list for everything else.

```python
# claims/service.py
def get_disclosable_status(claim: MotorClaim, verification_level: VerificationLevel) -> ClaimStatusRead:
    data = ClaimStatusRead.model_validate(claim)
    if verification_level != VerificationLevel.L2 and claim.claim_stage in _FINANCIAL_STAGES:
        data = data.model_copy(update={"settlement_amount": None})
    return data
```

### 0.9 Complaint SLA policy is a small `BaseSettings` subclass, not an insurer-configurable table

Spec §18.1 requires `acknowledgment_due_at`/`resolution_due_at` "computed deterministically
... from insurer-configured SLA policy," but a real per-insurer policy administration UI is
out of Phase 1's scope (no dashboard screens exist yet — Phase 3+). Same reasoning as
`telephony/`'s contact-calendar stub: `complaints/config.py::ComplaintsConfig(BaseSettings)`
holds `ACKNOWLEDGMENT_SLA_HOURS: int = 24` / `RESOLUTION_SLA_DAYS: int = 9`, and
`complaints/service.py` computes the two `_due_at` timestamps from these at creation time —
env-overridable, never LLM-estimated, never client-settable (no field for either exists on
`ComplaintCreate`, per `CLAUDE.md` §2.4). A real insurer-administered policy table is a
later-phase upgrade that swaps this module's internals without touching its callers.

---

## 1. Domain package layout — the Phase 0 → Phase 1 diff

Everything already in `backend/src/` (read in full above) stays; this is what's added.
Unmarked files are new; `(+)` marks a Phase-0 file gaining new content.

```
backend/
├── src/
│   ├── customers/
│   │   ├── models.py (+)          # + CustomerContactPreference, CustomerAuthFactor
│   │   ├── schemas.py
│   │   └── service.py             # get_contact_preference(), get_auth_factor()
│   ├── claims/
│   │   ├── router.py              # GET /claims/* — spec §27 Claims section
│   │   ├── schemas.py             # ClaimStatusRead, ClaimTimelineRead, ...
│   │   └── service.py             # get_disclosable_status() — see 0.8
│   ├── campaigns/
│   │   ├── __init__.py
│   │   ├── models.py              # OutboundCampaign, CallJob
│   │   ├── schemas.py
│   │   ├── service.py             # check_call_eligibility() — see 0.6
│   │   ├── workflows.py           # RetrySchedulerWorkflow — see 0.1
│   │   ├── activities.py          # dial_attempt, eligibility-check activities
│   │   ├── dependencies.py
│   │   ├── constants.py           # ATTEMPT_WINDOWS, MAX_ATTEMPTS = 3
│   │   └── exceptions.py
│   ├── telephony/
│   │   ├── __init__.py
│   │   ├── models.py              # TelephonyCliConfiguration, BusinessContactCalendar
│   │   ├── schemas.py
│   │   └── service.py             # validate_cli(), is_within_contact_window()
│   ├── calls/
│   │   ├── models.py              # CallAttempt, CallSession — see 0.3
│   │   ├── schemas.py             # CustomerIntentSignal + variants, CallSessionRead
│   │   ├── router.py              # GET /calls/{callId}, POST /calls, .../events, .../outcome, .../callback
│   │   ├── service.py             # create_call_attempt(), finalize_outcome()
│   │   ├── workflows.py (+)       # CallSessionWorkflow — real implementation, see §3
│   │   ├── activities.py (+)      # + right-party/auth/status/action-dispatch activities
│   │   ├── disposition.py         # resolve_disposition() — see §9
│   │   ├── dependencies.py        # valid_call_attempt
│   │   └── exceptions.py
│   ├── verification/
│   │   ├── __init__.py
│   │   ├── models.py              # VerificationAttempt, OtpChallenge
│   │   ├── schemas.py
│   │   ├── service.py             # verify_level1(), send_otp(), verify_otp()
│   │   ├── constants.py           # VerificationLevel, MAX_AUTH_ATTEMPTS, OTP_* defaults
│   │   ├── config.py              # VerificationConfig(BaseSettings) — see 0.7
│   │   ├── adapters/
│   │   │   └── otp_delivery/
│   │   │       ├── base.py
│   │   │       └── log_only.py
│   │   └── exceptions.py
│   ├── actions/
│   │   ├── models.py              # ClaimAction, Escalation, Callback
│   │   ├── schemas.py
│   │   ├── router.py              # POST /claims/{claimId}/actions, /escalations
│   │   ├── service.py             # create_action(), create_escalation(), schedule_callback() — idempotent
│   │   └── dependencies.py
│   ├── complaints/
│   │   ├── __init__.py
│   │   ├── models.py              # Complaint, ComplaintSlaEvent
│   │   ├── schemas.py             # no acknowledgment_due_at/resolution_due_at on Create — see CLAUDE.md §2.4
│   │   ├── router.py              # POST /complaints, GET /complaints/{id}
│   │   ├── service.py             # create_complaint() — idempotent, computes SLA timestamps
│   │   ├── workflows.py           # ComplaintSlaMonitorWorkflow — durable timers, §18.1
│   │   ├── activities.py
│   │   ├── config.py              # ComplaintsConfig(BaseSettings) — see 0.9
│   │   └── constants.py
│   ├── audit/
│   │   └── models.py (+)          # + RuntimeFailureEvent
│   ├── calls/constants.py (+)     # CallState — full enum, replacing the Phase-0 placeholder
│   └── main.py (+)                # + claims_router, calls_router, actions_router, complaints_router
├── worker.py (+)                  # registers CallSessionWorkflow, RetrySchedulerWorkflow,
│                                   #   ComplaintSlaMonitorWorkflow + their activities;
│                                   #   deletes _phase0_worker_boot_probe (see worker.py's own docstring)
├── scripts/
│   └── seed_demo_data.py (+)      # + CustomerContactPreference/CustomerAuthFactor rows,
│                                   #   a demo TelephonyCliConfiguration, an always-open BusinessContactCalendar
└── tests/
    ├── unit/
    │   ├── test_call_state_machine_transitions.py
    │   ├── test_disposition_resolution.py    # table-driven — see §9
    │   ├── test_verification_otp_state_machine.py
    │   ├── test_complaint_sla_computation.py
    │   └── test_eligibility_checks.py
    └── integration/
        └── test_phase1_e2e.py     # the 15-branch harness — see §0.5 and §12
```

---

## 2. Data model (task 1)

### 2.1 `customers/models.py` additions

```python
class CustomerContactPreference(Base):
    __tablename__ = "customer_contact_preference"
    id: Mapped[str] = mapped_column(primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customer.id"), index=True, unique=True)
    preferred_language: Mapped[str] = mapped_column(default="en")   # "en" | "ar"
    preferred_contact_window_start: Mapped[str | None] = mapped_column(default=None)  # "HH:MM"
    preferred_contact_window_end: Mapped[str | None] = mapped_column(default=None)


class CustomerAuthFactor(Base):
    """One row per Level-1 knowledge factor the customer has on file. `factor_value_hash`
    only — spec §10.2's factors (partial Emirates ID, birth month/year, partial plate) are
    never stored or compared in plaintext, same discipline as OTP (§36 rule 18's spirit)."""
    __tablename__ = "customer_auth_factor"
    id: Mapped[str] = mapped_column(primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customer.id"), index=True)
    factor_type: Mapped[str]          # "EID_LAST4" | "BIRTH_MONTH_YEAR" | "PLATE_LAST4"
    factor_value_hash: Mapped[str]    # sha256, same fingerprint helper as src/idempotency.py
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

### 2.2 `campaigns/models.py`

```python
class OutboundCampaign(Base):
    __tablename__ = "outbound_campaign"
    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    reason: Mapped[str]               # e.g. "REPAIR_AUTHORIZED" — spec §4's example `reason`
    priority: Mapped[str] = mapped_column(default="NORMAL")  # NORMAL | URGENT
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CallJob(Base):
    """One per (campaign, customer, claim) — the unit RetrySchedulerWorkflow is keyed on."""
    __tablename__ = "call_job"
    id: Mapped[str] = mapped_column(primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("outbound_campaign.id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customer.id"), index=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("motor_claim.id"), index=True)
    status: Mapped[str] = mapped_column(default="QUEUED")  # QUEUED | IN_PROGRESS | DONE
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

### 2.3 `telephony/models.py`

```python
class TelephonyCliConfiguration(Base):
    __tablename__ = "telephony_cli_configuration"
    cli: Mapped[str] = mapped_column(primary_key=True)     # "+971XXXXXXXXX"
    owner: Mapped[str]
    trunk_authorized: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)


class BusinessContactCalendar(Base):
    """Stub per task 4 — one row per exceptional day. Absence of a row for a date means
    'normal contact window applies'; real Ramadan/holiday data is a Phase 5 concern."""
    __tablename__ = "business_contact_calendar"
    id: Mapped[str] = mapped_column(primary_key=True)
    calendar_date: Mapped[date] = mapped_column(index=True)
    calendar_type: Mapped[str]        # "HOLIDAY" | "RAMADAN" | "BLACKOUT"
    contact_allowed: Mapped[bool] = mapped_column(default=False)
```

### 2.4 `calls/models.py`

```python
class CallAttempt(Base):
    """One row per dial — see decision 0.3. Written before dialing (QUEUED) and finalized
    by CallSessionWorkflow's terminal activity regardless of outcome."""
    __tablename__ = "call_attempt"
    id: Mapped[str] = mapped_column(primary_key=True)
    call_job_id: Mapped[str | None] = mapped_column(ForeignKey("call_job.id"), index=True, default=None)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customer.id"), index=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("motor_claim.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(default=1)
    attempted_at: Mapped[datetime] = mapped_column(server_default=func.now())
    answer_result: Mapped[str | None] = mapped_column(default=None)   # spec §5's classification
    disposition_code: Mapped[str] = mapped_column(
        SAEnum(DispositionCode, name="disposition_code", validate_strings=True,
               native_enum=False, create_constraint=True, length=64)
    )
    # spec §23 structured outcome fields
    customer_reached: Mapped[bool] = mapped_column(default=False)
    right_party: Mapped[bool | None] = mapped_column(default=None)
    verified: Mapped[bool] = mapped_column(default=False)
    verification_level: Mapped[str | None] = mapped_column(default=None)
    status_delivered: Mapped[str | None] = mapped_column(default=None)
    resolution: Mapped[str | None] = mapped_column(default=None)
    duration_seconds: Mapped[int | None] = mapped_column(default=None)
    # spec §6.10 retry-engine fields
    next_attempt_at: Mapped[datetime | None] = mapped_column(default=None)
    voicemail_detected: Mapped[bool] = mapped_column(default=False)
    attempts_remaining: Mapped[int | None] = mapped_column(default=None)


class CallSession(Base):
    """Created only on HumanAnswered — see decision 0.3. Mirrors spec §10.6.2 exactly."""
    __tablename__ = "call_session"
    id: Mapped[str] = mapped_column(primary_key=True)
    call_attempt_id: Mapped[str] = mapped_column(ForeignKey("call_attempt.id"), index=True, unique=True)
    state: Mapped[str]                                    # CallState value
    right_party_confirmed: Mapped[bool] = mapped_column(default=False)
    verification_level: Mapped[str] = mapped_column(default="L0")
    status_already_disclosed: Mapped[bool] = mapped_column(default=False)
    pending_action: Mapped[str | None] = mapped_column(default=None)
    last_committed_event_id: Mapped[str | None] = mapped_column(default=None)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
```

### 2.5 `verification/models.py`

```python
class VerificationAttempt(Base):
    __tablename__ = "verification_attempt"
    id: Mapped[str] = mapped_column(primary_key=True)
    call_session_id: Mapped[str] = mapped_column(ForeignKey("call_session.id"), index=True)
    level: Mapped[str]                # "L1" | "L2"
    factor_type: Mapped[str | None] = mapped_column(default=None)
    outcome: Mapped[str]              # "MATCH" | "NO_MATCH"
    attempted_at: Mapped[datetime] = mapped_column(server_default=func.now())


class OtpChallenge(Base):
    """code_hash only — spec §10.3.2/§36 rule 18: never store OTP in plaintext."""
    __tablename__ = "otp_challenge"
    id: Mapped[str] = mapped_column(primary_key=True)
    call_session_id: Mapped[str] = mapped_column(ForeignKey("call_session.id"), index=True)
    code_hash: Mapped[str]
    sent_count: Mapped[int] = mapped_column(default=1)
    attempt_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(default="SENT")   # SENT|VERIFIED|EXPIRED|LOCKED
    expires_at: Mapped[datetime]
    locked_until: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

### 2.6 `actions/models.py`

```python
class ClaimAction(Base):
    __tablename__ = "claim_action"
    id: Mapped[str] = mapped_column(primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("motor_claim.id"), index=True)
    source_call_id: Mapped[str | None] = mapped_column(default=None)
    action_code: Mapped[str] = mapped_column(
        SAEnum(ActionCode, name="action_code", validate_strings=True,
               native_enum=False, create_constraint=True, length=64)
    )
    summary: Mapped[str]
    status: Mapped[str] = mapped_column(default="OPEN")   # OPEN | CLOSED
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Escalation(Base):
    __tablename__ = "escalation"
    id: Mapped[str] = mapped_column(primary_key=True)
    call_id: Mapped[str] = mapped_column(index=True)
    reason: Mapped[str]
    context_snapshot: Mapped[dict] = mapped_column(JSONB)   # spec §19.1's warm-transfer context
    status: Mapped[str] = mapped_column(default="OPEN")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Callback(Base):
    __tablename__ = "callback"
    id: Mapped[str] = mapped_column(primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customer.id"), index=True)
    claim_id: Mapped[str | None] = mapped_column(default=None)
    callback_window_start: Mapped[datetime]
    callback_window_end: Mapped[datetime]
    reason: Mapped[str]               # "CUSTOMER_DRIVING" | "CUSTOMER_UNAVAILABLE" | ...
    status: Mapped[str] = mapped_column(default="SCHEDULED")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

### 2.7 `complaints/models.py`

```python
class Complaint(Base):
    __tablename__ = "complaint"
    id: Mapped[str] = mapped_column(primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("motor_claim.id"), index=True)
    source_call_id: Mapped[str]
    complaint_category: Mapped[str]
    customer_statement_summary: Mapped[str]
    customer_expected_resolution: Mapped[str | None] = mapped_column(default=None)
    severity: Mapped[str]              # LOW | MEDIUM | HIGH
    preferred_contact_method: Mapped[str]  # PHONE | EMAIL | SMS
    status: Mapped[str] = mapped_column(default="OPEN")
    acknowledgment_due_at: Mapped[datetime]     # computed server-side only — see 0.9
    resolution_due_at: Mapped[datetime]
    sla_source: Mapped[str] = mapped_column(default="INSURER_CONFIGURED")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ComplaintSlaEvent(Base):
    """Insert-only, same discipline as AuditEvent (CLAUDE.md §2.5) — an SLA clock's history
    must never be edited, only appended to."""
    __tablename__ = "complaint_sla_event"
    id: Mapped[str] = mapped_column(primary_key=True)
    complaint_id: Mapped[str] = mapped_column(ForeignKey("complaint.id"), index=True)
    event_type: Mapped[str]           # "AT_RISK" | "BREACHED"
    deadline_kind: Mapped[str]        # "ACKNOWLEDGMENT" | "RESOLUTION"
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

### 2.8 `audit/models.py` addition

```python
class RuntimeFailureEvent(Base):
    """CLAUDE.md's audit/ bullet places this here, not in calls/ — see phase-1-backend-spec
    §0.4. Insert-only, same three-layer enforcement as AuditEvent (§2.5/§2.6 of Phase 0's
    audit/models.py — extend the same before_update/before_delete listeners to this class)."""
    __tablename__ = "runtime_failure_event"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    call_id: Mapped[str | None] = mapped_column(index=True, default=None)
    component: Mapped[str]            # "LLM" | "STT" | "TTS" | "BACKEND" | "ORCHESTRATOR" | "TELEPHONY"
    failure_type: Mapped[str]         # spec §10.6's LLM_TIMEOUT | BACKEND_5XX | ... vocabulary
    recovery_action: Mapped[str]      # WARM_TRANSFER_IF_AVAILABLE | HUMAN_CALLBACK_CREATED | SAFE_TERMINATION
    consumed_retry_attempt: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

Migration ordering: one Alembic revision per package above, in FK dependency order
(`customers` → `telephony`/`campaigns` → `calls` → `verification`/`actions`/`complaints` →
`audit`), matching the pattern already established by
`migrations/versions/2026-08-27_initial_schema.py`.

---

## 3. Master Call State Machine (task 2)

### 3.1 `calls/constants.py::CallState` — the full enum

Replaces the Phase 0 placeholder (`calls/constants.py`'s current docstring already says
"Phase 1 replaces this with spec §3's full Master Call State Machine"). Names follow spec
§3's mermaid diagram plus the subset of §3.1's global interrupts this phase actually drives
(per §0.4): `CALL_DROPPED`, `HUMAN_REQUEST`, `SYSTEM_DATA_UNAVAILABLE`,
`RUNTIME_COMPONENT_FAILURE`. The remaining interrupts (`ADVERSARIAL_INPUT_DETECTED`,
`CUSTOMER_VULNERABILITY_INDICATED`, `FRAUD_SUSPECTED`, `LEGAL_SENSITIVITY_DETECTED`,
`ACCESSIBILITY_REQUIREMENT_DETECTED`, `RECORDING_CONSENT_REFUSED`,
`COMMUNICATION_SUPPRESSION_REQUEST`, `DSAR_OR_PRIVACY_RIGHTS_REQUEST`,
`SAFETY_OR_SECURITY_ESCALATION`) are **named as a `FrozenSet[str]` of reserved future
signal names** (`FUTURE_GLOBAL_INTERRUPTS` in the same module) so Phase 2/5 extend the
signal surface without renaming anything Phase 1 shipped — but `CallSessionWorkflow` does
not handle them yet.

```python
class CallState(StrEnum):
    CALL_QUEUED = "CALL_QUEUED"
    DIALING = "DIALING"
    NO_ANSWER = "NO_ANSWER"
    VOICEMAIL = "VOICEMAIL"
    HUMAN_ANSWERED = "HUMAN_ANSWERED"
    FAILED = "FAILED"
    INTRODUCTION = "INTRODUCTION"
    RIGHT_PARTY_CHECK = "RIGHT_PARTY_CHECK"
    WRONG_PARTY = "WRONG_PARTY"
    CUSTOMER_UNAVAILABLE = "CUSTOMER_UNAVAILABLE"
    AUTHENTICATION = "AUTHENTICATION"
    AUTH_RETRY = "AUTH_RETRY"
    AUTHENTICATED = "AUTHENTICATED"
    AUTH_FAILED = "AUTH_FAILED"
    PURPOSE_DISCLOSURE = "PURPOSE_DISCLOSURE"
    STATUS_DELIVERY = "STATUS_DELIVERY"
    FOLLOW_UP = "FOLLOW_UP"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    COMPLAINT = "COMPLAINT"
    HUMAN_ESCALATION = "HUMAN_ESCALATION"
    CALLBACK_REQUESTED = "CALLBACK_REQUESTED"
    CALLBACK_SCHEDULE = "CALLBACK_SCHEDULE"
    RESOLVED = "RESOLVED"
    RESOLUTION_SUMMARY = "RESOLUTION_SUMMARY"
    TRANSFER_OR_CALLBACK = "TRANSFER_OR_CALLBACK"
    CLOSE = "CLOSE"
```

### 3.2 `calls/workflows.py::CallSessionWorkflow`

```python
@workflow.defn
class CallSessionWorkflow:
    def __init__(self) -> None:
        self._state = CallState.CALL_QUEUED
        self._pending_signal: CustomerIntentSignal | None = None
        self._call_dropped = False

    @workflow.signal
    async def customer_utterance(self, intent: CustomerIntentSignal) -> None:
        self._pending_signal = intent

    @workflow.signal
    async def otp_response(self, code: str) -> None:
        self._pending_signal = CustomerIntentSignal(intent="OTP_ANSWER", value=code)

    @workflow.signal
    async def human_request_detected(self) -> None:
        self._pending_signal = CustomerIntentSignal(intent="REQUEST_HUMAN")

    @workflow.signal
    async def call_dropped(self) -> None:
        self._call_dropped = True

    @workflow.query
    def current_state(self) -> str:
        return self._state

    @workflow.run
    async def run(self, inp: CallSessionInput) -> CallSessionOutput:
        attempt = await workflow.execute_activity(
            create_call_attempt, inp, start_to_close_timeout=timedelta(seconds=10)
        )
        self._state = CallState.DIALING
        answer = await workflow.execute_activity(
            classify_answer, attempt.id, start_to_close_timeout=timedelta(seconds=30)
        )

        if answer != "HUMAN_ANSWERED":
            return await self._finalize_no_conversation(attempt, answer)

        self._state = CallState.HUMAN_ANSWERED
        session = await workflow.execute_activity(
            create_call_session, attempt.id, start_to_close_timeout=timedelta(seconds=10)
        )

        outcome = await self._run_right_party_and_beyond(attempt, session)
        return await self._finalize(attempt, session, outcome)

    async def _wait_for_signal(self, timeout: timedelta) -> CustomerIntentSignal | None:
        self._pending_signal = None
        try:
            await workflow.wait_condition(
                lambda: self._pending_signal is not None or self._call_dropped, timeout=timeout
            )
        except asyncio.TimeoutError:
            return None
        if self._call_dropped:
            return None
        signal, self._pending_signal = self._pending_signal, None
        return signal

    # ... _run_right_party_and_beyond / _run_authentication / _run_status_and_follow_up /
    # _finalize_no_conversation / _finalize are private helper methods, one per state-machine
    # stage, each executing the relevant activity and branching on _wait_for_signal()'s
    # result or the deterministic activity result. This mirrors spec §3's diagram directly —
    # no stage is collapsed or reordered relative to the mermaid source.
```

Every state transition — not just the terminal one — also executes
`record_audit_event` (Phase 0's activity, reused as-is) with the transition's
`decision`/`reason_code`, matching spec §32's shape. This is what lets the exit criteria be
verified "by reading the `AuditEvent` rows," per the phase file's own wording, without a
separate `CallEvent` table (deferred per §0.4).

`self._call_dropped` handling: any `_wait_for_signal` call that returns because
`call_dropped()` fired immediately routes to `_finalize` with
`CALL_DROPPED_PRE_AUTH`/`CALL_DROPPED_POST_AUTH` depending on whether `session.verification_level`
had reached `L1`/`L2` yet — this is the literal code shape of spec §10.6.3's rule (verification
authority is bound to the live call session and expires on disconnect); no separate
"resume" code path exists because there is nothing to resume — a redial starts a brand-new
`CallSessionWorkflow` execution with `right_party_confirmed = False` again by construction.

### 3.3 Execution-timeout + lock configuration

```python
# calls/constants.py
MAX_CALL_SESSION_SECONDS = 900   # bounded TTL, spec §4.1 — see decision 0.2
```

```python
# campaigns/workflows.py, starting the child:
await workflow.start_child_workflow(
    CallSessionWorkflow.run, call_input,
    id=f"call-session-{job.customer_id}",
    id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
    execution_timeout=timedelta(seconds=MAX_CALL_SESSION_SECONDS),
    parent_close_policy=ParentClosePolicy.ABANDON,
)
```

---

## 4. Mock claims API (task 3)

`claims/router.py` implements spec §27's Claims section against the Phase 0
`claims/models.py` tables (already fully built — nothing new to migrate here):

```python
GET /claims/{claim_id}            -> ClaimRead
GET /claims/{claim_id}/status     -> ClaimStatusRead   # spec §12 shape, via get_disclosable_status()
GET /claims/{claim_id}/timeline   -> list[ClaimStatusEventRead]
GET /claims/{claim_id}/documents  -> list[ClaimDocumentRead]
GET /claims/{claim_id}/garage     -> RepairGarageRead | None
```

`GET /claims/{claim_id}/status` is the one route that takes `verification_level` as a query
parameter (not inferred from an auth header, since Phase 1 has no dashboard-user auth yet —
`auth/` is unscheduled per `phase-0-frontend-spec.md` decision 1) and returns the redacted
shape from §0.8. Every route uses `Depends(valid_claim)` (new `claims/dependencies.py`,
following the `valid_call_session` pattern `CLAUDE.md` §2.2 already documents) instead of a
repeated fetch-or-404 in each function body.

This is also what `calls/activities.py`'s status-delivery activity calls internally — the
router and the workflow activity share the same `claims/service.py` function, never
duplicate the lookup.

---

## 5. Call orchestrator / eligibility (task 4)

### 5.1 `campaigns/service.py::check_call_eligibility`

```python
async def check_call_eligibility(session: AsyncSession, *, job: CallJob) -> CallEligibility:
    claim = await claims_service.get_claim(session, job.claim_id)
    cli = await telephony_service.get_active_cli(session)
    contact_ok = await telephony_service.is_within_contact_window(session, workflow.now() if workflow.in_workflow() else datetime.now(UTC))

    return CallEligibility(
        call_eligible=bool(claim) and cli.trunk_authorized and contact_ok,  # not suppressed — see 0.6
        customer_id=job.customer_id,
        claim_id=job.claim_id,
        cli=cli.cli,
        cli_trunk_authorized=cli.trunk_authorized,
        contact_window_allowed=contact_ok,
        # suppression intentionally hardcoded True (not suppressed) — see decision 0.6
    )
```

Called from a `campaigns/activities.py` activity (never directly from workflow code — it
touches the database), at the top of `RetrySchedulerWorkflow.run` and again before each
retry attempt (a contact window that was open at attempt 1 may not be at attempt 2's later
time). If ineligible, `RetrySchedulerWorkflow` records the specific reason
(`INVALID_OR_UNAUTHORIZED_CLI` if `cli_trunk_authorized` is false, else a generic
`CALL_NOT_ELIGIBLE` audit decision) via `record_audit_event` and does not start a
`CallSessionWorkflow` child at all — this attempt is never dialed, so no `CallAttempt` row
consumes one of the customer's 3 retry slots for it (spec §4.1: "abort the AI attempt
without consuming a customer retry attempt" — extended here to any pre-dial ineligibility,
not just the lock conflict).

### 5.2 `telephony/service.py`

```python
async def get_active_cli(session: AsyncSession) -> TelephonyCliConfiguration: ...
async def is_within_contact_window(session: AsyncSession, at: datetime) -> bool:
    """True unless an active BusinessContactCalendar row for `at.date()` sets
    contact_allowed=False. Stub: with no seeded blackout rows, every date is open — task 4's
    'contact-calendar stub' requirement, real data lands in Phase 5."""
```

Both functions are also called directly from `RetrySchedulerWorkflow`'s per-attempt
activities (not just the initial eligibility gate) — the calendar in particular must be
re-checked at each of spec §6's three attempt windows independently, since a call scheduled
during Ramadan-adjusted hours for attempt 1 might land outside the window entirely for
attempt 2's later retry.

---

## 6. Authentication service (task 5)

### 6.1 `verification/constants.py`

```python
class VerificationLevel(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"

MAX_AUTH_ATTEMPTS = 2            # spec §10.4
OTP_TTL_SECONDS = 180            # spec §10.3.2
MAX_OTP_SENDS_PER_SESSION = 2
MAX_OTP_ATTEMPTS = 3
OTP_RESEND_COOLDOWN_SECONDS = 30
OTP_LOCKOUT_MINUTES = 30
```

All five OTP values are re-declared as fields on `verification/config.py::VerificationConfig`
(defaulting to the constants above) rather than left as bare module constants — spec
§10.3.2's own text says "these values are deployment defaults and must remain
configurable," the same requirement §2.2.1 states for the latency constants, which
`CLAUDE.md` §2.8 already resolves via `BaseSettings` subclasses per domain.

### 6.2 `verification/service.py`

```python
async def verify_level1(session, *, call_session_id: str, factor_type: str, supplied_value: str) -> VerificationAttempt:
    """One MAX_AUTH_ATTEMPTS-counted attempt. Compares supplied_value's hash against
    CustomerAuthFactor.factor_value_hash — never the plaintext (see 2.1)."""

async def send_otp(session, *, call_session_id: str, phone_e164: str) -> OtpChallenge:
    """Enforces MAX_OTP_SENDS_PER_SESSION and OTP_RESEND_COOLDOWN_SECONDS before generating
    a new code; delegates delivery to the configured OtpDeliveryAdapter (see 0.7)."""

async def verify_otp(session, *, challenge_id: str, supplied_code: str) -> OtpChallenge:
    """Enforces MAX_OTP_ATTEMPTS; on the (MAX_OTP_ATTEMPTS+1)th failure sets status=LOCKED
    and locked_until = now + OTP_LOCKOUT_MINUTES, and the caller (calls/activities.py) maps
    that to DispositionCode.OTP_ATTEMPTS_EXCEEDED / OTP_LOCKED."""
```

`MAX_AUTH_ATTEMPTS` (Level 1) and `MAX_OTP_ATTEMPTS` (Level 2) are two independent counters
against two independent tables (`VerificationAttempt` vs. `OtpChallenge.attempt_count`) —
spec §10.3.2 is explicit that OTP controls are "independent from Level 1 knowledge-based
authentication," so `calls/activities.py`'s authentication stage tracks both, and a customer
failing Level 1 twice reaches `AUTH_FAILED` without ever touching the OTP path (Level 2 is
only invoked for actions that explicitly require it, per spec §10.3 "use for higher-risk
actions" — Phase 1's harness exercises it directly for the `OTP LIMIT → lockout` branch
without necessarily routing through a failed Level 1 first).

`CallSession.verification_level` (never `Customer`, per §36 rule 28, already true by
construction since `Customer` has no such column) is what `calls/activities.py` writes after
each successful `verify_level1`/`verify_otp` call — `verification/service.py` itself never
touches `CallSession`, keeping the domain boundary: `verification/` decides pass/fail,
`calls/` owns what that means for session state.

---

## 7. Status engine (task 6)

Covered in design decision 0.8. The only new artifact beyond `claims/service.py`'s
`get_disclosable_status()` is the constant set of financial stages it checks against:

```python
# claims/constants.py addition
_FINANCIAL_STAGES = frozenset({ClaimStage.SETTLEMENT_APPROVED, ClaimStage.PAYMENT_INITIATED})
```

`calls/activities.py`'s status-delivery activity calls `get_disclosable_status()` and writes
the result's `approved_customer_message_key` onto `CallAttempt.status_delivered` — this is
the field the disposition resolver (§9) and the exit-criteria assertions read, since Phase 1
never renders the key into actual spoken/written text.

Type A/B follow-up questions (spec §14) reuse the exact same activity — `ASK_QUESTION`
signal variants (`{"intent": "ASK_QUESTION", "topic": "GARAGE"}`,
`{"intent": "ASK_QUESTION", "topic": "ETA"}`, `{"intent": "ASK_QUESTION", "topic": "NEXT_STEP"}`)
map to `claims/service.py` field reads (`claim.garage_id` → `RepairGarage`, `claim.expected_by`,
`claim.next_expected_event`) rather than free-text answers — this is what proves the
`QUESTION → grounded answer` branch without an LLM: the answer is a structured field, not
generated prose.

---

## 8. Action / escalation / complaint service (task 7)

### 8.1 `actions/service.py` — idempotent creates

```python
async def create_action(session, *, key: str, correlation_id: str, claim_id: str,
                         action_code: ActionCode, summary: str, source_call_id: str | None) -> ClaimAction:
    result = await idempotent(
        session, key=key, correlation_id=correlation_id, operation_name="create_action",
        payload={"claim_id": claim_id, "action_code": action_code, "summary": summary},
        operation=lambda: _insert_action(session, claim_id, action_code, summary, source_call_id),
    )
    return ClaimAction(**result)
```

`create_escalation` and `schedule_callback` follow the identical shape against `Escalation`
and `Callback`. `complaints/service.py::create_complaint` follows the same shape but also
computes the two SLA timestamps (§0.9) inside the same idempotent operation closure, so a
retried complaint creation never recomputes a different due-date on replay (the *first*
successful computation is what the idempotency record freezes and returns).

`Idempotency-Key` format, matching spec §10.6.4's example verbatim:
`f"{call_id}-ACTION-{sequence}"`, minted by `calls/activities.py` (one sequence counter per
call, incremented per action/escalation/complaint/callback the state machine creates during
that call) — never left to the caller to invent ad hoc, so two activities in the same call
can never accidentally collide on the same key.

### 8.2 `complaints/workflows.py::ComplaintSlaMonitorWorkflow`

```python
@workflow.defn
class ComplaintSlaMonitorWorkflow:
    @workflow.run
    async def run(self, inp: ComplaintSlaMonitorInput) -> None:
        for deadline_kind, due_at in (("ACKNOWLEDGMENT", inp.acknowledgment_due_at),
                                       ("RESOLUTION", inp.resolution_due_at)):
            warn_at = due_at - timedelta(hours=settings.COMPLAINT_SLA_WARNING_HOURS)
            await workflow.sleep(warn_at - workflow.now())
            if not await workflow.execute_activity(is_deadline_cleared, inp.complaint_id, deadline_kind, ...):
                await workflow.execute_activity(raise_complaint_sla_event, ..., event_type="AT_RISK")
                await workflow.execute_activity(create_action, ..., action_code=ActionCode.COMPLAINT_SLA_ESCALATION)
            await workflow.sleep(due_at - workflow.now())
            if not await workflow.execute_activity(is_deadline_cleared, inp.complaint_id, deadline_kind, ...):
                await workflow.execute_activity(raise_complaint_sla_event, ..., event_type="BREACHED")
                await workflow.execute_activity(create_action, ..., action_code=ActionCode.COMPLAINT_SLA_ESCALATION)
```

Started (as a detached top-level workflow, `id=f"complaint-sla-{complaint_id}"`, not a
child of `CallSessionWorkflow` — it must keep running long after the call itself ends) by
`complaints/service.py::create_complaint` in the same transaction that inserts the
`Complaint` row, via a Temporal client call from the calling activity. This is the durable
timer `CLAUDE.md` §2.6 describes ("`complaints`'s SLA-monitoring workflow sleeps until the
configured warning threshold... survives a process restart because Temporal persists
workflow state") — no cron job, no external scheduler.

---

## 9. Disposition engine (task 8)

`calls/disposition.py::resolve_disposition` is a pure function — no I/O, fully unit-testable
against a truth table — called once by `CallSessionWorkflow`'s final activity:

```python
def resolve_disposition(ctx: DispositionContext) -> DispositionCode:
    """ctx carries only already-decided facts (final CallState, whether authenticated,
    whether an action/complaint/escalation was created, OTP lock status, call-drop flag) —
    never re-derives anything from raw signal history. One pure match, no side effects."""
    match ctx.final_state:
        case CallState.CLOSE if ctx.status_delivered and ctx.question_resolved:
            return DispositionCode.SUCCESS_STATUS_AND_QUERY_RESOLVED
        case CallState.CLOSE if ctx.status_delivered:
            return DispositionCode.SUCCESS_STATUS_DELIVERED
        case CallState.CLOSE if ctx.complaint_created:
            return DispositionCode.SUCCESS_COMPLAINT_REGISTERED
        case CallState.CLOSE if ctx.action_created:
            return DispositionCode.SUCCESS_ACTION_CREATED
        case CallState.CLOSE if ctx.human_transferred:
            return DispositionCode.SUCCESS_HUMAN_TRANSFER
        case CallState.WRONG_PARTY:
            return DispositionCode.WRONG_PARTY
        case CallState.CUSTOMER_UNAVAILABLE:
            return DispositionCode.RIGHT_PARTY_NOT_AVAILABLE
        case CallState.AUTH_FAILED:
            return DispositionCode.AUTH_FAILED
        case _ if ctx.otp_locked:
            return DispositionCode.OTP_LOCKED
        case _ if ctx.otp_attempts_exceeded:
            return DispositionCode.OTP_ATTEMPTS_EXCEEDED
        case _ if ctx.call_dropped and not ctx.was_authenticated:
            return DispositionCode.CALL_DROPPED_PRE_AUTH
        case _ if ctx.call_dropped:
            return DispositionCode.CALL_DROPPED_POST_AUTH
        case _ if ctx.callback_requested:
            return DispositionCode.CALLBACK_REQUESTED
        case _ if ctx.backend_unavailable:
            return DispositionCode.BACKEND_SYSTEM_FAILURE
        case _:
            raise UnresolvedDispositionError(ctx)
```

`resolve_disposition` never raises `UnresolvedDispositionError` in production use — the
exception exists so `tests/unit/test_disposition_resolution.py` can assert every branch the
workflow can actually reach has a case (a new `CallState` added later without a matching
disposition rule fails this test immediately, not silently at runtime).

### 9.1 Disposition codes reachable in Phase 1 vs. deferred

Of the 46 codes in `calls/constants.py::DispositionCode` (all already defined in Phase 0),
Phase 1's harness produces exactly these, matching the phase file's 15-branch exit criteria
plus the two the SLA/eligibility work in tasks 4 and 7 add for free:

`SUCCESS_STATUS_DELIVERED`, `SUCCESS_STATUS_AND_QUERY_RESOLVED`, `SUCCESS_ACTION_CREATED`,
`SUCCESS_COMPLAINT_REGISTERED`, `SUCCESS_HUMAN_TRANSFER`, `CALLBACK_REQUESTED`,
`HUMAN_CALLBACK_REQUIRED`, `RIGHT_PARTY_NOT_AVAILABLE`, `WRONG_PARTY`, `AUTH_FAILED`,
`NO_ANSWER`, `CONCURRENT_CALL_CONFLICT`, `BACKEND_SYSTEM_FAILURE`,
`CALL_DROPPED_PRE_AUTH`, `CALL_DROPPED_POST_AUTH`, `OTP_ATTEMPTS_EXCEEDED`, `OTP_LOCKED`,
`INVALID_OR_UNAUTHORIZED_CLI`, `COMPLAINT_SLA_AT_RISK`, `COMPLAINT_SLA_BREACHED`.

Everything else in the enum (`LINE_BUSY`, `CALL_REJECTED`, `VOICEMAIL`,
`NUMBER_UNREACHABLE`, `AUTOMATED_CONTACT_UNSUCCESSFUL` — telephony-layer answer results not
distinguishable without real telephony; `LLM_TIMEOUT`, `STT_SERVICE_FAILURE`,
`TTS_SERVICE_FAILURE`, `DTMF_FALLBACK_ACTIVATED` — Phase 2; `ADVERSARIAL_INPUT_DETECTED`,
`SECURITY_POLICY_ESCALATION`, `CUSTOMER_VULNERABILITY_INDICATED`, `FRAUD_SUSPECTED`,
`MINOR_ANSWERED`, `ACCESSIBILITY_REQUIREMENT_DETECTED`, `DSAR_REQUESTED`,
`CONSENT_REFUSED`, `COMMUNICATION_SUPPRESSION_REQUESTED`,
`HIGH_RISK_NUMBER_CHANGE_DETECTED`, `SPECIAL_CUSTOMER_CIRCUMSTANCE`,
`SILENT_CALL_TECHNICAL_FAILURE`, `AI_ESCALATED_LOW_CONFIDENCE`,
`CUSTOMER_TERMINATED_CALL`, `AUTH_REFUSED`, `NETWORK_FAILURE`,
`INVALID_CONTACT_NUMBER` — Phase 2/5) remains defined in the shared enum (so nothing needs
renaming later) but is not producible by any Phase 1 code path. The CI gate from
`phase-0-backend-spec.md` §3.4 (`check_disposition_action_codes.py`) still protects every
one of them the moment a later phase's code assigns one.

---

## 10. No-answer / retry scheduler (task 9)

### 10.1 `campaigns/workflows.py::RetrySchedulerWorkflow`

```python
@workflow.defn
class RetrySchedulerWorkflow:
    @workflow.run
    async def run(self, inp: RetrySchedulerInput) -> None:
        for attempt_number in (1, 2, 3):
            if not await workflow.execute_activity(check_call_eligibility_activity, inp.job_id, ...):
                return  # ineligible this window — no attempt consumed, see §5.1

            try:
                result = await self._run_one_attempt(inp, attempt_number)
            except ChildWorkflowError as exc:
                if isinstance(exc.cause, WorkflowAlreadyStartedError):
                    await workflow.execute_activity(finalize_call_job, inp.job_id,
                                                      DispositionCode.CONCURRENT_CALL_CONFLICT)
                    continue  # does not consume a retry slot — retry the SAME attempt_number next window
                raise

            if result.disposition_code not in (DispositionCode.NO_ANSWER, DispositionCode.VOICEMAIL):
                return  # answered (successfully or not) — retry engine's job is done

            if attempt_number == 3:
                await self._handle_attempts_exhausted(inp)
                return

            next_window = ATTEMPT_WINDOWS[attempt_number]  # spec §6.1 — different time bucket per attempt
            await workflow.sleep(next_window.delay_from(workflow.now()))
```

`_handle_attempts_exhausted` implements spec §6.9's critical-status override directly:

```python
async def _handle_attempts_exhausted(self, inp: RetrySchedulerInput) -> None:
    criticality = await workflow.execute_activity(get_status_criticality, inp.claim_id, ...)
    disposition = DispositionCode.AUTOMATED_CONTACT_UNSUCCESSFUL
    await workflow.execute_activity(finalize_call_job, inp.job_id, disposition)
    if criticality in ("ACTION_REQUIRED", "URGENT"):
        await workflow.execute_activity(
            create_action, key=f"job-{inp.job_id}-EXHAUSTED", correlation_id=inp.job_id,
            claim_id=inp.claim_id, action_code=ActionCode.HUMAN_CALLBACK_CREATED,
            summary="Automated contact attempts exhausted for action-required status",
        )
```

`get_status_criticality` is a small pure lookup (`ADDITIONAL_APPROVAL_REQUIRED`,
`ADDITIONAL_INFORMATION_REQUIRED`, `SETTLEMENT_APPROVED` → `"ACTION_REQUIRED"`;
`CLAIM_DECLINED` → `"URGENT"`; everything else → `"NORMAL"`), living in
`claims/constants.py` next to `_FINANCIAL_STAGES` (§7) since it's the same kind of
`ClaimStage`-keyed table.

### 10.2 `campaigns/constants.py::ATTEMPT_WINDOWS`

```python
ATTEMPT_WINDOWS: dict[int, RetryWindow] = {
    1: RetryWindow(min_delay=timedelta(hours=2), max_delay=timedelta(hours=6)),
    2: RetryWindow(min_delay=timedelta(hours=2), max_delay=timedelta(hours=4)),  # spec §6.1: "at least 2-4 hours later"
}
MAX_ATTEMPTS = 3
```

Per spec §6.2 ("avoid calling at exactly the same time repeatedly"), the actual sleep
duration is randomized within `[min_delay, max_delay]` — but `workflow.random()` (Temporal's
deterministic, replay-safe RNG), never `random.random()`, per `CLAUDE.md` §2.6's "no
`datetime.now()`/`random()` inside workflow code" rule.

---

## 11. Runtime failure / recovery controller (task 10)

`calls/activities.py` wraps every activity that calls an external dependency (claims lookup,
verification, action/complaint creation) with a shared decorator that catches timeouts and
maps them to spec §10.6.1's response:

```python
# calls/activities.py
def with_runtime_recovery(component: str, failure_type_default: str):
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(fn(*args, **kwargs), timeout=settings.BACKEND_SOFT_WAIT_MS / 1000)
            except (TimeoutError, ConnectionError) as exc:
                await audit_service_record_runtime_failure(component=component, failure_type=failure_type_default, ...)
                raise BackendUnavailableError(component) from exc
        return wrapper
    return decorator

@activity.defn
@with_runtime_recovery(component="BACKEND", failure_type_default="BACKEND_TIMEOUT")
async def fetch_claim_status_activity(claim_id: str) -> ClaimStatusRead: ...
```

`BackendUnavailableError`, caught in `CallSessionWorkflow`'s status-delivery stage, routes to
`DispositionContext.backend_unavailable = True` (→ `BACKEND_SYSTEM_FAILURE`, §9) and — if
the action-creation activity itself is still reachable — creates a
`BACKEND_DATA_VERIFICATION_REQUEST` action via the same idempotent path as every other
action (§8.1), matching spec §14 Type E's "if the action API is available, create an
idempotent follow-up task." If action-creation *also* fails, the workflow does not retry
indefinitely — Temporal's own activity retry policy (bounded: 3 attempts,
exponential backoff, configured on `execute_activity`'s `RetryPolicy`) governs that, and
exhausting it surfaces as the same `BACKEND_SYSTEM_FAILURE` disposition with
`RuntimeFailureEvent.recovery_action = "SAFE_TERMINATION"` — this is what proves the
`BACKEND FAILURE → deterministic recovery` branch without the workflow ever improvising
a customer-specific answer (spec §36 rule 26).

`src/config.py` gains the two latency constants spec §2.2.1 recommends
(`BACKEND_SOFT_WAIT_MS: int = 1500`, already implied by the activity timeout above) —
`MODEL_TIMEOUT_MS`/`TARGET_TURN_P95_MS` are **not** added yet, since they govern the
LLM/TTS turn latency chain that doesn't exist until Phase 2.

---

## 12. The fake/text conversation harness (exit-criteria mechanism)

`tests/integration/test_phase1_e2e.py` — one test function per branch, following the same
`WorkflowEnvironment` + in-test `Worker` pattern Phase 0 established
(`phase-0-backend-spec.md` §4.3), now against the real `CallSessionWorkflow`/
`RetrySchedulerWorkflow`:

```python
async def test_normal_customer_status_delivered(temporal_env, db_session, seeded_customer_claim):
    async with Worker(temporal_env.client, task_queue="phase1-e2e",
                       workflows=[CallSessionWorkflow], activities=[...ALL_CALLS_ACTIVITIES]):
        handle = await temporal_env.client.start_workflow(
            CallSessionWorkflow.run, CallSessionInput(...), id="call-session-CUST-DEMO-001",
            task_queue="phase1-e2e",
        )
        await handle.signal(CallSessionWorkflow.customer_utterance, CustomerIntentSignal(intent="RIGHT_PARTY_CONFIRMED"))
        await handle.signal(CallSessionWorkflow.customer_utterance,
                             CustomerIntentSignal(intent="AUTH_ANSWER", value="<seeded factor value>"))
        result = await handle.result()

    assert result.disposition_code == DispositionCode.SUCCESS_STATUS_DELIVERED
    attempt = await db_session.get(CallAttempt, ...)
    assert attempt.verified and attempt.verification_level == "L1"
    audit_rows = (await db_session.execute(select(AuditEvent).where(AuditEvent.call_id == attempt.id))).scalars().all()
    assert any(e.decision == "STATUS_DELIVERED" for e in audit_rows)
```

The 15 tests together are the literal exit-criteria proof — each asserts both the
`CallAttempt.disposition_code` and the `AuditEvent` trail, per the phase file's own
"verified by reading the `AuditEvent`/outcome-record rows" requirement. `NO_ANSWER → retry`
and `CONCURRENT_CALL_CONFLICT` are tested via `RetrySchedulerWorkflow`, not
`CallSessionWorkflow` directly, since retry scheduling is that workflow's job.

`seeded_customer_claim` (a `tests/conftest.py` fixture) reuses
`scripts/seed_demo_data.py`'s fixed-ID synthetic dataset (already required to cover all 18
`ClaimStage` values per `phase-0-backend-spec.md` §4.2) — no test hand-crafts a claim row.

---

## 13. API surface additions

New routers registered in `main.py`, each `Depends(require_outbound_enabled(...))`-gated
where it can trigger a dial (per `CLAUDE.md` §2.2's kill-switch rule):

```text
GET  /claims/{claim_id}                          claims_router
GET  /claims/{claim_id}/status                   claims_router
GET  /claims/{claim_id}/timeline                 claims_router
GET  /claims/{claim_id}/documents                claims_router
GET  /claims/{claim_id}/garage                   claims_router

GET  /calls/{call_id}                            calls_router
POST /calls                                      calls_router   -> Depends(require_outbound_enabled("ai_automation"))
POST /calls/{call_id}/events                     calls_router   (dashboard-facing debug/replay use only)
GET  /calls/{call_id}/outcome                     calls_router

POST /claims/{claim_id}/actions                  actions_router
POST /claims/{claim_id}/escalations              actions_router
POST /calls/{call_id}/callback                    actions_router

POST /complaints                                  complaints_router
GET  /complaints/{complaint_id}                    complaints_router

POST /calls/eligibility/check                      campaigns_router  -> Depends(require_outbound_enabled("campaign"))
GET  /telephony/cli/{cli}/validation               telephony (mounted under campaigns_router's tags for now — no
                                                     dedicated dashboard screen exists yet to justify a 5th router)
```

`POST /calls` starts a `CallSessionWorkflow` directly (bypassing `RetrySchedulerWorkflow`) —
this is the ad-hoc single-attempt entry point spec §27 implies and is also what
`tests/integration/test_phase1_e2e.py` calls under the hood via the Temporal client
directly rather than going through HTTP (no FastAPI test client dependency needed for the
workflow-level proof). `response_model=CallAttemptRead` on every route, per `CLAUDE.md`
§2.2 — nothing internal (e.g., `CallSession.pending_action`'s raw value) leaks past what the
schema declares.

---

## 14. Migrations

One Alembic revision per new/changed table group, hand-reviewed per `CLAUDE.md` §2.5
(autogenerate is a draft, not the commit):

1. `customers` additions (`CustomerContactPreference`, `CustomerAuthFactor`)
2. `campaigns` (`OutboundCampaign`, `CallJob`)
3. `telephony` (`TelephonyCliConfiguration`, `BusinessContactCalendar`)
4. `calls` (`CallAttempt`, `CallSession`)
5. `verification` (`VerificationAttempt`, `OtpChallenge`)
6. `actions` (`ClaimAction`, `Escalation`, `Callback`)
7. `complaints` (`Complaint`, `ComplaintSlaEvent`)
8. `audit` addition (`RuntimeFailureEvent`) + a hand-written follow-up migration extending
   the Phase 0 `REVOKE UPDATE, DELETE` grant (`migrations/versions/2026-08-27_audit_event_insert_only_grants.py`'s
   pattern) to `runtime_failure_event` and `complaint_sla_event` — both are append-only for
   the same reason `audit_event` is (§2.5/§2.8 above).

`scripts/seed_demo_data.py` gains: one `CustomerContactPreference` + one
`CustomerAuthFactor` per seeded customer (so every demo customer can actually pass Level 1),
one active `TelephonyCliConfiguration` row, and zero `BusinessContactCalendar` rows (the
"stub" state — every date open by default, per §5.2).

---

## 15. CI updates

`.github/workflows/backend-ci.yml` needs no new *steps* — the existing pipeline (governance
gates → tests → compose smoke test) already covers this phase's additions, since the two
Phase 0 static-analysis gates (`check_tool_allowlist.py`, `check_disposition_action_codes.py`)
extend automatically to any new file under `src/`. One addition: the Temporal-backed
integration tests in `tests/integration/test_phase1_e2e.py` need the same `temporal`
service already running in CI for `test_phase0_e2e.py` — no new service definition required.

---

## 16. Exit criteria traceability

| Branch (`phases/phase-1-deterministic-core.md`) | Disposition | Proven by |
|---|---|---|
| `NO ANSWER → retry` | `NO_ANSWER` | `RetrySchedulerWorkflow` sleep+redial test, §10/§12 |
| `BUSY CUSTOMER → callback` | `CALLBACK_REQUESTED` | `actions/service.py::schedule_callback` via `CUSTOMER_DRIVING` intent, §8.1 |
| `WRONG PERSON → privacy-safe termination` | `WRONG_PARTY` | `_run_right_party_and_beyond`'s `WRONG_PARTY` branch, §3.2 |
| `AUTH FAILURE → disclosure blocked` | `AUTH_FAILED` | `verification/service.py::verify_level1` × `MAX_AUTH_ATTEMPTS`, §6.2 |
| `NORMAL CUSTOMER → status delivered` | `SUCCESS_STATUS_DELIVERED` | `claims/service.py::get_disclosable_status`, §7 |
| `QUESTION → grounded answer` | `SUCCESS_STATUS_AND_QUERY_RESOLVED` | `ASK_QUESTION` intent → claims field read, §7 |
| `DISPUTE → action created` | `SUCCESS_ACTION_CREATED` | `DOCUMENT_STATUS_DISPUTE` action, §8.1 |
| `DISSATISFACTION → escalation` | `SUCCESS_ACTION_CREATED` / `SUCCESS_HUMAN_TRANSFER` | `CLAIM_DELAY_ESCALATION` action or `create_escalation`, §8.1 |
| `COMPLAINT → complaint created` | `SUCCESS_COMPLAINT_REGISTERED` | `complaints/service.py::create_complaint`, §8.1–8.2 |
| `HUMAN REQUEST → transfer/callback` | `SUCCESS_HUMAN_TRANSFER` / `HUMAN_CALLBACK_REQUIRED` | `human_request_detected` signal, §3.2 |
| `BACKEND FAILURE → deterministic recovery` | `BACKEND_SYSTEM_FAILURE` | `with_runtime_recovery`, §11 |
| `OTP LIMIT → lockout` | `OTP_ATTEMPTS_EXCEEDED` / `OTP_LOCKED` | `verification/service.py::verify_otp`, §6.2 |
| `CALL DROP → auth expires` | `CALL_DROPPED_PRE_AUTH` / `CALL_DROPPED_POST_AUTH` | `call_dropped` signal + no-resume-by-construction, §3.2 |
| `CONCURRENT CALL → AI attempt aborted` | `CONCURRENT_CALL_CONFLICT` | `WorkflowAlreadyStartedError` catch, §0.1/§0.2/§10.1 |
| `SUCCESS → summary + structured resolution` | `SUCCESS_STATUS_DELIVERED` (+ outcome fields) | `CallAttempt`'s §23 fields, §2.4/§9 |

All 15 verified via `AuditEvent`/`CallAttempt` rows per §12, not log inspection, matching
the phase file's own exit-criteria wording exactly.

---

## 17. Explicitly deferred to later phases

Keeping Phase 1 scoped to what its own exit criteria require, same discipline
`phase-0-backend-spec.md` §8 and `phase-0-frontend-spec.md` §6 already established:

- Real STT/LLM/TTS, `voice/pipeline.py`, and turning `CustomerIntentSignal` into something
  extracted from real speech → Phase 2. This phase's signal *shape* does not change when
  that lands (§0.5's entire point).
- `knowledge/` FAQ service, real Type D "out of scope" handling, sentiment classification,
  `CallTranscript`/`CallSummary`/`CustomerIntent`/`SentimentEvent`, the dashboard and its
  analytics → Phase 3.
- `communication_suppressions` (both the table and the live "stop calling me" interrupt),
  DSAR/privacy routing, PII redaction pipeline, `risk/` (fraud/vulnerability/legal-sensitivity),
  minor/accessibility/DTMF handling, recording-consent branching, adversarial-input defense
  beyond the tool allow-list already built in Phase 0 → Phase 5.
- A real per-insurer-configurable SLA-policy and contact-calendar administration surface
  (dashboard screens to edit `BusinessContactCalendar`/complaint SLA hours) → Phase 3
  (dashboard) once there's a screen to put it on; the underlying tables/config this phase
  builds don't need to change shape for that, only gain a UI.
- Ops-dashboard authentication (`auth/` domain) — still unscheduled per
  `phase-0-frontend-spec.md` decision 1; this phase's new routes carry no user-identity
  dependency yet, same as Phase 0's `/health`.
- Frontend work of any kind — nothing in `frontend/` changes in this phase. Phase 1
  produces real call data for the first time; wiring dashboard screens against it is
  `phase-1-frontend-spec.md`'s job, not this document's.
