# Phase 1 Backend — Implementation Plan

## Context

`.claude/specs/phase-1-backend-spec.md` is the finalized engineering design for Phase 1
("Deterministic Core") of the Insurance Outbound AI Call Center backend — the Master Call
State Machine, mock claims API, authentication/OTP service, action/complaint/escalation
services, disposition engine, no-answer retry scheduler, and runtime-failure recovery, all
driven end-to-end through a fake/text conversation harness with no real voice component yet.
It was written against the actual Phase 0 code already in `backend/src/` (models, audit
infrastructure, tool allow-list, kill switch, idempotency wrapper — all already built and
tested) and is the largest, highest-stakes phase in this repo: a bug here (an auth bypass, a
non-idempotent write, a wrong disposition code) would ship invisibly into every later phase.

This plan turns that spec into an ordered sequence of implementation batches. A second
review pass (a Plan-mode subagent, prompted specifically to validate sequencing and flag
integration risk against the *actual* test fixtures and Temporal sandbox conventions already
in the repo — not just the spec's own text) surfaced three real corrections to the spec's
code sketches and eight concrete risk areas; both are folded into this plan below rather than
kept as a separate critique document.

**Execution:** all 15 batches are implemented in one continuous push (confirmed with the
user) — the checkpoint inside Batch 11 is an internal verification milestone, not a pause
point.

**Batching principle:** every batch leaves the repo importable, `alembic upgrade head` clean
from empty, `pytest backend/tests` green (plus whatever that batch adds), and
`tests/unit/test_migrations_registry.py` satisfied. Models/migrations come before any
service touches them; pure functions (disposition resolution, constants) come before
anything that calls them; DB-backed-but-Temporal-free services come before anything
Temporal-shaped; `CallSessionWorkflow` (which calls activities which call services) comes
last among the workflow code, `RetrySchedulerWorkflow` after that since it starts
`CallSessionWorkflow` as a child.

**Step 0 — persist this plan as a project artifact.** Before batch 1, write this plan's
content to `.claude/specs/../plans/phase-1-backend-implementation-plan.md` — actually:
`.claude/plans/phase-1-backend-implementation-plan.md` in the repo root (the project already
has an empty `.claude/plans/` directory) — mirroring how `.claude/specs/phase-0-backend-spec.md`
and `.claude/specs/phase-1-backend-spec.md` are kept as durable repo artifacts, not just
harness-internal state.

---

## Corrections to the spec (apply these, not the literal original sketches)

1. **Concurrent-call exception shape.** The spec's §0.1 sketch catches
   `WorkflowAlreadyStartedError` directly; its §10.1 sketch (written later in the same
   document) correctly catches `ChildWorkflowError` and checks `isinstance(exc.cause,
   WorkflowAlreadyStartedError)` — that's the real shape a child-workflow start failure
   takes in Temporal's Python SDK. **Implement the §10.1 shape everywhere**; the §0.1 sketch
   is wrong and would silently fail to catch the concurrent-call case at all.
2. **OTP dev-only debug query must not read `settings.ENVIRONMENT` from inside
   `calls/workflows.py`.** Reading `pydantic-settings`-backed config from inside sandboxed
   workflow code is both a sandbox-import risk (see risk table below) and non-deterministic
   in spirit. Instead: decide `expose_debug_otp: bool` once, outside the workflow (at
   workflow-start time, e.g. set by the test harness or a non-production-only FastAPI
   dependency), and pass it as a plain field on `CallSessionInput`. `CallSessionWorkflow`
   itself never touches `settings`.
3. **`campaigns/service.py::check_call_eligibility` must not branch on
   `workflow.in_workflow()`.** The spec's §5.1 sketch does
   `workflow.now() if workflow.in_workflow() else datetime.now(UTC)` inside a plain service
   function — this violates `CLAUDE.md` §2.6 ("no `datetime.now()`/`random()` inside
   workflow code") in spirit and mixes framework awareness into a service module that should
   stay framework-agnostic like every other `service.py`. **Fix:** `check_call_eligibility`
   takes `at: datetime` as a required parameter; only `campaigns/activities.py`'s activity
   wrapper decides whether that's `workflow.now()` (never called — activities aren't inside
   workflow sandbox, so this doesn't apply there either) or wall-clock time. The activity is
   the one place that supplies `at`.

---

## Implementation batches

### Batch 1 — `customers`/`campaigns`/`telephony` models, no behavior
- `customers/models.py` (+): `CustomerContactPreference`, `CustomerAuthFactor`
- `campaigns/` (new package): `__init__.py`, `models.py` — `OutboundCampaign`, `CallJob`
- `telephony/` (new package): `__init__.py`, `models.py` — `TelephonyCliConfiguration`,
  `BusinessContactCalendar`
- Three chained Alembic revisions (one per package), hand-reviewed per `CLAUDE.md` §2.5
- Add `import src.campaigns.models` / `import src.telephony.models` to `migrations/env.py`
  (required or `tests/unit/test_migrations_registry.py` fails immediately)
- **Verify:** `alembic upgrade head` from empty; existing `pytest backend/tests/unit` green

### Batch 2 — `calls`/`verification`/`actions`/`complaints` models, no behavior
- `calls/models.py` (new): `CallAttempt`, `CallSession` (per spec §0.3 — two tables, not
  one; `CallSession` created only on `HumanAnswered`)
- `verification/` (new package): `__init__.py`, `models.py` — `VerificationAttempt`,
  `OtpChallenge`
- `actions/models.py` (+): `ClaimAction`, `Escalation`, `Callback`
- `complaints/` (new package): `__init__.py`, `models.py` — `Complaint`, `ComplaintSlaEvent`
- One migration per package, `migrations/env.py` updated with all four new imports
- `CallAttempt.disposition_code` / `ClaimAction.action_code` use the
  `SAEnum(DispositionCode/ActionCode, native_enum=False, create_constraint=True, length=64)`
  pattern already proven in Phase 0 against `MotorClaim.claim_stage`
- **Write a focused test here, not deferred:** insert a `CallAttempt` with an invalid
  `disposition_code` string and assert it's rejected by the CHECK constraint — proves the
  enum enforcement before any workflow code depends on it existing
- **Verify:** migrations apply cleanly; hand-check each generated CHECK constraint's literal
  list has exactly `len(DispositionCode)` / `len(ActionCode)` members (autogenerate can
  silently produce a truncated subset if the enum import context is wrong)

### Batch 3 — `audit/models.py` addition + insert-only grant extension
- `audit/models.py` (+): `RuntimeFailureEvent`
- Hand-written migration extending `REVOKE UPDATE, DELETE, TRUNCATE` (all three — copy the
  exact privilege set from `migrations/versions/2026-08-27_audit_event_insert_only_grants.py`;
  trimming to just `UPDATE, DELETE` reopens the exact hole that migration's own docstring
  warns about) to `runtime_failure_event` and `complaint_sla_event`
- Extend the same `before_update`/`before_delete`/`do_orm_execute` listener pattern from
  `audit/models.py` to `RuntimeFailureEvent`
- **Write the insert-only test before the migration**, mirroring
  `tests/unit/test_audit_insert_only.py`, asserting the app-role connection cannot `UPDATE`,
  `DELETE`, or `TRUNCATE` either new table — so the migration is written against a failing
  test, not reviewed by eye

### Batch 4 — test infrastructure: TRUNCATE list + time-skipping Temporal fixture
- `tests/conftest.py::db_session_committed` — add every new table from Batches 1–3 to the
  hardcoded `TRUNCATE` list. Postgres `CASCADE` will transitively clean up most FK-linked
  new tables automatically, but **these have no FK back to the original 9-table list and
  must be added explicitly**: `outbound_campaign`, `telephony_cli_configuration`,
  `business_contact_calendar`, `escalation` (its `call_id` is a plain indexed string, not an
  FK), `runtime_failure_event` (same — plain string `call_id`, mirroring `AuditEvent`'s
  precedent). Confirm `callagent_migrator` (used via `admin_engine`) retains `TRUNCATE` on
  `runtime_failure_event`/`complaint_sla_event` after Batch 3's grant revocation — the
  fixture's teardown needs it even though the app role must not have it.
- `tests/integration/conftest.py` — add a second fixture, e.g. `temporal_time_skipping_env`,
  using `WorkflowEnvironment.start_time_skipping()`. The existing `temporal_env` fixture is
  explicitly documented as non-time-skipping (fine for Phase 0's timer-free smoke workflow);
  `RetrySchedulerWorkflow`'s multi-hour `workflow.sleep` calls and
  `ComplaintSlaMonitorWorkflow`'s day-scale sleeps will hang/timeout real-wall-clock tests
  without it.
- **Extract the sandboxed workflow runner into a shared module** (e.g.
  `src/workflow_runner.py`) exporting the `SandboxedWorkflowRunner(restrictions=
  SandboxRestrictions.default.with_passthrough_modules("pydantic", "src"))` construction
  currently private to `tests/integration/test_phase0_e2e.py`. Both `worker.py` (Batch 11+)
  and `tests/integration/test_phase1_e2e.py` (Batch 12+) will need the identical
  configuration — `worker.py` currently constructs `Worker(...)` with no `workflow_runner=`
  at all, which means it's implicitly using the *stricter* default sandbox restrictions,
  not the ones Phase 0 already proved necessary. Write a one-line smoke test now ("worker.py
  can construct its `Worker(...)` with a dummy workflow importing `src.calls.constants`
  without raising a sandbox-restriction error at construction time") before Batch 11's real
  state-machine logic exists, so this question is answered before it's buried under
  unrelated debugging noise.

### Batch 5 — pure functions and constants (zero I/O, cheapest to review)
- `calls/constants.py` (+): full `CallState` enum replacing the Phase 0 placeholder, plus
  `FUTURE_GLOBAL_INTERRUPTS` (frozenset of reserved-but-unhandled signal names),
  `MAX_CALL_SESSION_SECONDS`
- `calls/disposition.py` (new): `DispositionContext`, `resolve_disposition()` — pure match
  statement per spec §9
- `campaigns/constants.py` (new): `ATTEMPT_WINDOWS`, `MAX_ATTEMPTS = 3`
- `verification/constants.py` (new): `VerificationLevel`, `MAX_AUTH_ATTEMPTS`, OTP defaults
- `claims/constants.py` (+): `_FINANCIAL_STAGES`, `get_status_criticality()`
- **Write `tests/unit/test_disposition_resolution.py` and
  `tests/unit/test_call_state_machine_transitions.py` here, first** — `resolve_disposition`
  is what every later branch's exit-criteria assertion depends on; get its truth table right
  in isolation before any workflow code consumes it. Table-driven: one row per `CallState` →
  `DispositionCode` mapping, asserting `UnresolvedDispositionError` for any `CallState` not
  yet covered (a regression guard for when a state is added later without a matching rule).

### Batch 6 — leaf domain services (DB-backed, no Temporal)
- `telephony/service.py` (new): `validate_cli()`, `is_within_contact_window()`
- `customers/service.py` (new): `get_contact_preference()`, `get_auth_factor()`
- `claims/service.py` (new): `get_disclosable_status()` (per spec §0.8 — key selection +
  Level-2 financial-field redaction)
- `verification/service.py`, `verification/config.py`, `verification/adapters/otp_delivery/`
  (`base.py` Protocol, `log_only.py` adapter, dev-only debug surfaced per the corrected
  design above — a plain input field, not a live settings read)
- Order within batch: telephony + customers first (independent of each other), then claims
  (depends only on Phase-0 `claims/models.py`), then verification last (depends on
  `customers/service.py::get_auth_factor` + its own Batch-2 models)
- **Tests:** `tests/unit/test_verification_otp_state_machine.py`, a claims-status-redaction
  unit test — all testable with the existing `db_session`/`db_session_committed` fixtures,
  no `temporal_env` needed

### Batch 7 — `campaigns/service.py::check_call_eligibility`
- Composes Batch 6's three services per spec §0.6/§5.1, corrected to take `at: datetime` as
  a parameter (see corrections above) rather than branching on `workflow.in_workflow()`
- `campaigns/dependencies.py`, `campaigns/exceptions.py`
- **Test:** `tests/unit/test_eligibility_checks.py`

### Batch 8 — `actions/service.py` + `complaints/service.py` (idempotent creates)
- `actions/service.py`: `create_action()`, `create_escalation()`, `schedule_callback()` —
  all through `src/idempotency.py::idempotent()` (already built in Phase 0)
- `complaints/config.py::ComplaintsConfig(BaseSettings)` (§0.9 — `ACKNOWLEDGMENT_SLA_HOURS`,
  `RESOLUTION_SLA_DAYS`)
- `complaints/service.py::create_complaint()` — computes both `_due_at` timestamps inside
  the same idempotent operation closure (so a retried creation never recomputes a different
  deadline on replay)
- **Not yet wired to `ComplaintSlaMonitorWorkflow`** — that's Batch 15. Write and unit-test
  the SLA-timestamp computation in isolation first:
  `tests/unit/test_complaint_sla_computation.py`

### Batch 9 — `claims/router.py` (mock claims API, task 3)
- `claims/router.py`, `claims/dependencies.py` (`valid_claim`, following the
  `valid_call_session` pattern from `CLAUDE.md` §2.2), `claims/schemas.py`
- Routes: `GET /claims/{claim_id}`, `.../status` (takes `verification_level` query param —
  no dashboard auth exists yet), `.../timeline`, `.../documents`, `.../garage`
- Register `claims_router` in `main.py`
- Zero Temporal dependency — testable via `httpx`/FastAPI `TestClient` directly, proving the
  redaction-by-verification-level behavior end-to-end before any workflow exists

### Batch 10 — `calls/activities.py` real activities (not yet wired into a workflow)
- Right-party check, authentication (Level 1 + OTP dispatch), status-delivery, and
  action-dispatch activities, `with_runtime_recovery()` decorator (§11)
- `calls/service.py`: `create_call_attempt()`, `finalize_outcome()`
- All Pydantic models shared between `calls/workflows.py` and `calls/activities.py`
  (`CallSessionInput`/`CallSessionOutput`/`CustomerIntentSignal`) go in **`calls/schemas.py`**,
  imported by both — not defined in `activities.py` and re-imported into `workflows.py`.
  This keeps `calls/workflows.py`'s import graph limited to what the sandbox passthrough
  already covers (`pydantic`, `src`) and out of SQLAlchemy/`src.database`'s import chain,
  which `calls/activities.py` necessarily pulls in.
- Activities are plain `@activity.defn` functions — testable directly (call the Python
  function, or via a minimal in-test `Worker`) without `CallSessionWorkflow` existing

### Batch 11 — `calls/workflows.py::CallSessionWorkflow` (real implementation)
The single highest-risk batch — keep it its own reviewable unit, not squashed with Batch 10
or 12.
- Signals (`customer_utterance`, `otp_response`, `human_request_detected`, `call_dropped`),
  query (`current_state`, `debug_last_otp_code` per the corrected design), `_wait_for_signal`
  helper, private `_run_*` stage methods mirroring spec §3's mermaid diagram stage-by-stage
- **Signal-race handling:** the spec's sketch uses a single `self._pending_signal` slot,
  reset to `None` then waited on. Before trusting this, write a test that sends two signals
  back-to-back with no `await` in between (e.g. `customer_utterance` immediately followed by
  `call_dropped`) via the Temporal test environment and confirm no intent is silently
  dropped. If the single-slot design can't guarantee this, switch to a queue
  (`list[CustomerIntentSignal]`) instead — decide this with a test, not by inspection.
- **Idempotency-key sequencing:** the per-call `f"{call_id}-ACTION-{sequence}"` counter
  (spec §8.1) must live as workflow-instance state incremented only inside the
  `@workflow.run` coroutine itself (never inside a signal handler, which could race against
  the main coroutine and break replay determinism). Write a test with two concurrent
  `CallSessionWorkflow` runs against different `call_id`s asserting no
  `idempotency_record` primary-key collision.
- `execution_timeout=timedelta(seconds=MAX_CALL_SESSION_SECONDS)`,
  `id=f"call-session-{customer_id}"`, `id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE`
- Register `CallSessionWorkflow` + its activities in `worker.py`, using the shared sandboxed
  workflow runner from Batch 4, deleting `_phase0_worker_boot_probe`

**Internal checkpoint (not a scope cut — a verification milestone within this batch):**
before adding the full branching (`WRONG_PARTY`/`AUTH_FAILED`/`CALL_DROPPED`/OTP paths), get
`CALL_QUEUED → DIALING → HUMAN_ANSWERED → RIGHT_PARTY_CHECK → AUTHENTICATION (Level 1 only)
→ STATUS_DELIVERY → CLOSE` (→ `SUCCESS_STATUS_DELIVERED`) working end-to-end through a real
Temporal worker with one integration test, proving the full mechanism (signal in → activity
→ DB write → disposition → audit trail) before layering in the other 12 branches this
workflow handles. This is the cheapest point to catch a sandbox-import or exception-handling
mistake, before it's entangled with 14 more branches' worth of logic.

### Batch 12 — `tests/integration/test_phase1_e2e.py`, `CallSessionWorkflow`-only branches
The 13 of 15 exit-criteria branches reachable without `RetrySchedulerWorkflow`: normal
status delivered, question resolved, dispute → action, dissatisfaction → escalation,
complaint created, human request → transfer/callback, backend failure → recovery, OTP limit
→ lockout, call drop (pre/post auth), wrong party, auth failure, busy → callback, success +
summary. One shared harness file (per spec §12's `WorkflowEnvironment` + in-test `Worker` +
shared sandboxed runner pattern), each branch asserting both `CallAttempt.disposition_code`
and the resulting `AuditEvent` rows.

### Batch 13 — `campaigns/workflows.py::RetrySchedulerWorkflow` + `campaigns/activities.py`
- Starts `CallSessionWorkflow` as a child (`workflow.start_child_workflow`,
  `parent_close_policy=ParentClosePolicy.ABANDON` — a live call must not be torn down if the
  scheduler workflow itself exits)
- **Use the corrected exception shape** (see Corrections above):
  `except ChildWorkflowError as exc: if isinstance(exc.cause, WorkflowAlreadyStartedError): ...`
- `ATTEMPT_WINDOWS`-based randomized sleep using `workflow.random()` (never `random.random()`
  — hard Temporal determinism requirement), spec §6.9's critical-status-override handling via
  `claims/constants.py::get_status_criticality()` (Batch 5)
- Register in `worker.py`
- **Test:** a dedicated test starting two `CallSessionWorkflow`s for the same `customer_id`
  concurrently, asserting the second resolves to `CONCURRENT_CALL_CONFLICT` — do not trust
  the exception-handling sketch by inspection alone

### Batch 14 — remaining 2 `test_phase1_e2e.py` branches
`NO_ANSWER → retry` and `CONCURRENT_CALL → AI attempt aborted`, both via
`RetrySchedulerWorkflow`, using the Batch 4 time-skipping Temporal fixture.

### Batch 15 — complaint SLA workflow + remaining API surface + seed data
Can run in parallel with Batches 11–14 (no dependency on `CallSessionWorkflow`) if split
across contributors; sequenced last here as the lowest-risk, most mechanical batch.
- `complaints/workflows.py::ComplaintSlaMonitorWorkflow` (durable timers per spec §8.2),
  wired from `complaints/service.py::create_complaint` via a Temporal client call in the same
  transaction that inserts the `Complaint` row
- `calls/router.py`, `actions/router.py`, `complaints/router.py`, campaigns/telephony routes
  per spec §13 — all `Depends(require_outbound_enabled(...))`-gated where they can trigger a
  dial, per `CLAUDE.md` §2.2's kill-switch rule
- Register all new routers in `main.py`
- `scripts/seed_demo_data.py` (+): `CustomerContactPreference`/`CustomerAuthFactor` per
  seeded customer, one active `TelephonyCliConfiguration`, zero `BusinessContactCalendar`
  rows (stub state — every date open by default)
- Register `ComplaintSlaMonitorWorkflow` in `worker.py`

---

## Key risks & mitigations (condensed)

| # | Risk | Mitigation |
|---|---|---|
| 1 | Idempotency-key sequence counter racing against replay if touched from a signal handler | Increment only inside `@workflow.run`'s own coroutine; test concurrent runs for PK collisions (Batch 11) |
| 2 | Single-slot `_pending_signal` silently dropping a signal that arrives back-to-back with another | Test two signals with no `await` between them before trusting the design; fall back to a queue if needed (Batch 11) |
| 3 | Concurrent-call exception caught with the wrong exception type | Use `ChildWorkflowError`/`exc.cause` shape everywhere (Corrections §1) |
| 4 | `SAEnum(..., native_enum=False)` autogenerate producing a truncated CHECK constraint | Hand-verify generated constraint literal count matches `len(DispositionCode)`/`len(ActionCode)` (Batch 2) |
| 5 | OTP debug query reading live settings from inside sandboxed workflow code | Pass `expose_debug_otp` as a plain `CallSessionInput` field, decided outside the workflow (Corrections §2) |
| 6 | Grant-extension migration trimmed to `UPDATE, DELETE`, reopening the `TRUNCATE` hole | Write the insert-only test before the migration (Batch 3) |
| 7 | `RetrySchedulerWorkflow`'s multi-hour sleeps hanging real-wall-clock tests | Dedicated time-skipping Temporal fixture (Batch 4) |
| 8 | `workflow.in_workflow()` branching leaking into a plain service function | `check_call_eligibility` takes `at: datetime`, no framework awareness (Corrections §3) |
| 9 | `worker.py` implicitly using the *stricter* default sandbox (no `pydantic`/`src` passthrough) once real workflows are registered | Shared `src/workflow_runner.py`, smoke-tested before Batch 11's real logic (Batch 4) |
| 10 | New FK-less tables (`outbound_campaign`, `telephony_cli_configuration`, `business_contact_calendar`, `escalation`, `runtime_failure_event`) never cleaned up by `TRUNCATE ... CASCADE`, causing cross-test flake | Add all five explicitly to the TRUNCATE list (Batch 4) |

---

## Verification (overall, run after each batch and again at the end)

```bash
cd backend
.venv/bin/alembic upgrade head                              # from empty, on a clean DB
.venv/bin/python scripts/ci/check_tool_allowlist.py
.venv/bin/python scripts/ci/check_disposition_action_codes.py
.venv/bin/python scripts/ci/check_no_raw_prompt_concat.py
.venv/bin/pytest tests -v                                    # unit + integration
docker compose up -d --wait && curl -f http://localhost:8001/health && docker compose down -v
```

End-of-phase acceptance is the traceability table in `.claude/specs/phase-1-backend-spec.md`
§16 — all 15 exit-criteria branches verified via `AuditEvent`/`CallAttempt` rows (not log
inspection), matching `phases/phase-1-deterministic-core.md`'s own exit criteria wording.
Do not start Phase 2 work until every row in that table is green — per the phase file's own
Notes section, a bug here ships invisibly into every later phase.
