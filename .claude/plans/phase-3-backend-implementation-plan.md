# Phase 3 Backend — Implementation Plan

## Context

`.claude/specs/phase-3-backend-spec.md` is the finalized engineering design for Phase 3
("Operational Intelligence") of the Insurance Outbound AI Call Center backend — the
transcript PII-redaction pipeline (spec §28), conversation summaries, sentiment/
dissatisfaction classification (spec §18), and the `reporting/` dashboard-metrics layer
(spec §31). It was written against the actual Phase 1+2 code already in `backend/src/`
(commit `2514289`, "phase 2 backend") and turns several long-standing forward references in
that code — `calls/models.py`'s own docstring literally says "that's `CallTranscript`'s job,
Phase 3" — into real tables, services, and workflow wiring.

This plan turns that spec into an ordered sequence of implementation batches, the same way
`.claude/plans/phase-1-backend-implementation-plan.md` did for Phase 1. A dedicated Plan-mode
subagent, prompted specifically to validate batch sequencing and flag integration risk
against the actual current codebase (not just the spec's own prose), found one real,
precisely-located bug in the spec's own code sketch — folded in below as a correction, the
same way Phase 1's plan handled its own spec corrections, rather than by editing the spec
file itself.

**Execution:** all 12 batches are implemented in one continuous push (confirmed with the
user) — batch boundaries below are internal checkpoints and review units, not pause points.

**Batching principle**, identical to Phase 1's: every batch leaves the repo importable,
`alembic upgrade head` clean from empty, and `pytest backend/tests` green plus whatever that
batch adds. Models/migrations come before services; pure/no-I/O functions come before their
callers; DB-backed-but-Temporal-free code comes before anything Temporal-shaped. Unlike Phase
1 — which built `CallSessionWorkflow` from scratch — this phase's highest-risk batch (Batch
8) **edits already-working, already-tested production logic**, so the risk shape is
regression, not construction: it gets its own reviewable unit, and the full existing Phase
1+2 e2e suite is re-run after each of its five sub-changes, not just once at the end.

**Step 0 — persist this plan as a project artifact.** Write this plan's content to
`.claude/plans/phase-3-backend-implementation-plan.md` in the repo root, mirroring how
`.claude/plans/phase-1-backend-implementation-plan.md` and
`.claude/plans/phase-2-frontend-implementation-plan.md` are kept as durable repo artifacts.

---

## Corrections to the spec (apply these, not the literal sketches)

1. **`persist_transcript_turn`'s "one committed transaction" sketch (spec §3.4) violates the
   established `idempotent()` contract.** `src/idempotency.py::idempotent()` calls
   `session.commit()`/`session.rollback()` itself (`idempotency.py:92,94,120,145` —
   confirmed by direct read). `src/actions/service.py`'s own docstring is explicit: *"per
   that module's own docstring, `idempotent()` commits `session` itself — callers here must
   not (and do not) wrap these calls in an outer `async with session.begin():`."* Every
   existing caller of an `idempotent()`-backed service function
   (`actions_service.create_action`/`create_escalation`/`schedule_callback`,
   `complaints_service.create_complaint`) is invoked from `calls/activities.py` via plain
   `async with session_factory() as session:` — **no `.begin()`** (confirmed:
   `create_action`'s activity body has no `session.begin()` call, unlike
   `record_audit_event`/`finalize_outcome`/etc., which don't call `idempotent()` and do use
   `session.begin()`). The spec's §3.4 sketch wraps `persist_transcript_turn`'s whole body in
   `async with session_factory() as session, session.begin():` and then calls
   `privacy_service.record_redaction_events()` (which calls `idempotent()`, which commits)
   from inside that block — the exact class of mistake this codebase's own docstrings warn
   against.
   **Fix:** drop the outer `session.begin()`. Insert `CallTranscript` via a plain
   `session.add()` + explicit `await session.commit()` (matching `create_call_attempt`'s
   existing plain-insert shape), then call `record_redaction_events()` separately — it
   manages its own commits per detected category via `idempotent()`. This means the
   "atomically, never exists without its detection log" framing in spec §0.4/§3.4 is **not
   literally achievable** through the established idempotency primitive; document the
   resulting two-step-commit window explicitly in the function's docstring instead of
   asserting an atomicity guarantee the code doesn't actually provide.

2. **`CallTranscript` has no uniqueness protection against a duplicate direct call.** Unlike
   `PiiRedactionEvent` (protected by the `(call_id, turn_index, category)` idempotency key),
   `CallTranscript` is a plain UUID-PK insert. The spec accepts a *dropped* write as fine (one
   lost turn, not customer-impacting) but is silent on a *duplicated* write (e.g. a WebRTC
   reconnect replaying a frame). Add a unique constraint on
   `(call_attempt_id, turn_index, speaker)` at the model level (Batch 1) rather than leaving
   this an undecided gap.

3. **Signal-handling and idempotency-key-sequencing conventions from Phase 1 carry forward
   unchanged and must be honored by every new call site this phase adds** — confirmed by
   reading the current `calls/workflows.py`: `_next_action_key`'s counter is still only
   incremented inside `@workflow.run`'s own coroutine, never a signal handler, and the signal
   queue is still a list, not a single slot. Batch 8's four new `_record_intent` call sites
   and the `run()`/`_finalize()` additions must be written from the main coroutine the same
   way — flagged again in Batch 8 below since it's the batch most likely to violate this by
   accident (four near-identical-but-not-identical call sites is exactly the kind of place a
   copy-paste mistake slips in).

---

## Implementation batches

### Batch 1 — `privacy/` + `calls/` new models, no behavior
- `privacy/__init__.py`, `privacy/constants.py` (`PiiCategory` StrEnum), `privacy/models.py`
  (`PiiRedactionEvent`, `@enforce_insert_only` from `src/insert_only.py` — reused, not
  hand-rolled)
- `calls/models.py` (+): `CallTranscript` (with the Correction 2 unique constraint on
  `(call_attempt_id, turn_index, speaker)`), `CallSummary`, `CustomerIntent`,
  `SentimentEvent`, `CallLatencySample` — all `@enforce_insert_only`
- Two chained Alembic migrations off current HEAD `9e2f4a7c1b6d` (`privacy` then `calls`, per
  spec §7), each with a hand-written `REVOKE UPDATE, DELETE, TRUNCATE` (all three privileges
  — Phase 1 Batch 3's lesson: trimming to just `UPDATE, DELETE` reopens the exact hole that
  migration family exists to close)
- Add `import src.privacy.models` to `migrations/env.py`'s import block (currently at
  `migrations/env.py:22-31`, alphabetically between `src.customers.models` and
  `src.telephony.models`) — `tests/unit/test_migrations_registry.py` globs every
  `models.py` under `src/` and fails immediately if this is missed
- Hand-verify the `PiiCategory` `SAEnum(..., native_enum=False, length=32)` CHECK
  constraint's generated literal count == `len(PiiCategory)` — same autogenerate risk Phase 1
  Batch 2 already caught once
- **Add all 6 new tables explicitly** to `tests/conftest.py::db_session_committed`'s
  hardcoded TRUNCATE list (currently 25 tables at `tests/conftest.py:169-179`) — this repo's
  established convention is explicit-over-CASCADE, and `pii_redaction_event.call_id` has no
  FK at all (same reasoning as `Escalation.call_id`), so a miss here silently accumulates
  rows across test runs
- Write the insert-only tests **before** the migration lands, mirroring
  `tests/unit/test_audit_insert_only.py` — Phase 1 Batch 3's precedent
- **Verify:** `alembic upgrade head` from empty; `test_migrations_registry.py` green;
  insert-only tests reject UPDATE/DELETE/TRUNCATE from the app role on all 6 new tables; the
  new unique constraint rejects a duplicate `(call_attempt_id, turn_index, speaker)` insert

### Batch 2 — pure functions, zero I/O (cheapest to review)
- `privacy/scrubber.py`: IBAN (mod-97 checksum), CARD_NUMBER (Luhn checksum), EMIRATES_ID
  (format-only, no public checksum), PHONE_NUMBER, EMAIL_ADDRESS, POLICY_CLAIM_ID,
  OTP_PIN_CVV_PASSWORD (keyword-window, runs first, unconditional masking)
- `privacy/service.py::redact()` — pure; the deterministic layer always runs, the Presidio
  NER pass is gated on `language == "en"` (spec §2.4's documented Arabic-NER gap)
- `voice/sentiment.py::classify_sentiment()` — same shape as the existing `voice/guard.py`,
  pure lexicon match, no I/O; independent of `privacy/`, authored in parallel within this
  batch
- `requirements/base.txt` additions (`presidio-analyzer`, `presidio-anonymizer`, `spacy`) +
  a documented `python -m spacy download en_core_web_sm` step in `backend/README` —
  sequenced here rather than Batch 1 so the models/migrations batch stays free of a new
  heavy-dependency install risk. **Confirm the actual current compatible version pins for
  these three packages at implementation time** (via Context7 or the package index) rather
  than trusting any version numbers written into the spec verbatim — they were not verified
  against the live package index when the spec was drafted.
- **Tests, written first per Phase 1's precedent discipline:** `test_scrubber.py`
  (table-driven over spec §28's minimum-detect list + adversarial cases — the single most
  important test this phase adds, given spec §36 rule 17's severity), `test_iban_checksum.py`,
  `test_luhn_checksum.py`, `test_sentiment_classifier.py` (EN+AR, all 4 lexicon-detectable
  signals plus a benign-utterance false-positive guard)
- **Verify:** all green with zero DB/Temporal fixtures; confirm the spaCy model download
  actually succeeds in whatever environment will run CI before trusting the Presidio-path
  tests

### Batch 3 — `privacy/service.py::record_redaction_events()` (idempotent write)
- Depends on Batch 1 (model) + Batch 2 (`redact()`)
- Implements Correction 1's fixed transaction shape: plain `session_factory() as session:`
  (no `.begin()`), one `idempotent()` call per detected category, key
  `f"pii-redaction:{call_id}:{turn_index}:{category.value}"`
- **Test:** `test_pii_redaction_idempotency.py` — two calls with the identical
  `(call_id, turn_index)` key produce exactly one `PiiRedactionEvent` row per category
- **Verify:** zero-detection turns write nothing; concurrent duplicate calls don't raise or
  double-write

### Batch 4 — `calls/service.py` + `calls/schemas.py` additions (DB-backed, no Temporal)
- `record_transcript_turn` (Correction 1's shape), `get_redacted_transcript` (ordered by
  `turn_index` — the literal `CLAUDE.md` §1 worked example), `record_customer_intent`,
  `record_sentiment_event`, `record_call_summary`, `record_latency_sample`,
  `count_recent_attempts`
- `calls/schemas.py` (+): `Read` schemas for all 5 new models, `CallTranscriptTurnRead`
- Plain inserts/queries — testable directly against the `db_session`/`db_session_committed`
  fixtures, no `temporal_env` needed (same testability class as Phase 1 Batch 6)
- **Tests:** one per function; `get_redacted_transcript` returns `turn_index`-ordered rows;
  `count_recent_attempts` correctly windows on `attempted_at >= since` for a given
  `(customer_id, claim_id)` pair
- **Verify:** this module still imports nothing from `src.calls.activities`/Temporal (keeps
  the sandbox-safety boundary Phase 1 Batch 10 established between `schemas.py`/`service.py`
  and `activities.py`)

### Batch 5 — `calls/router.py` additions (4 new GET endpoints)
- `GET /{call_id}/transcript`, `/summary`, `/intents`, `/sentiment` — reuse the existing
  `valid_call_attempt` dependency, no new dependency introduced
- Depends only on Batch 4; zero Temporal dependency, same shape as Phase 1 Batch 9's
  `claims/router.py`
- **Test:** hit each endpoint against directly-seeded rows; confirm 404 for an unknown
  `call_id` via `valid_call_attempt`; confirm `/summary` returns `null` (not 404) when no
  `CallSummary` row exists yet
- **Verify:** routes registered under the existing `calls_router`; no auth dependency added
  (`src/auth/` doesn't exist yet — confirmed — consistent with every other route today)

### Batch 6 — `voice/adapters/llm/completion.py` + `gemini_completion.py`
- `CompletionAdapter` Protocol (`complete_json(system_prompt, user_prompt) -> dict`) + one
  Gemini-backed implementation, config-selected off the existing `voice_settings.LLM_PROVIDER`
- Independent of `calls/`; sequenced before Batch 7 only because `generate_call_summary`
  needs it
- **Decide explicitly here:** the adapter must be obtained through a small factory function
  that tests can monkeypatch, mirroring `verification/adapters/otp_delivery`'s
  `get_otp_delivery_adapter(config.OTP_DELIVERY_PROVIDER)` pattern already proven in this
  repo — otherwise `generate_call_summary` has no way to be unit-tested without a real
  Gemini call, breaking the "no real LLM in CI" discipline Phase 2 established
- **Test:** a `FakeCompletionAdapter` test double exercising the Protocol shape; no real API
  call in CI
- **Verify:** no new `.env.example` entries needed — reuses `GEMINI_API_KEY`
  (`.env.example:36`, already present)

### Batch 7 — `calls/activities.py` real activities (not yet wired into workflow or pipeline)
- `persist_transcript_turn` (Correction 1's shape), `record_customer_intent`,
  `record_sentiment_event`, `record_latency_sample`, `generate_call_summary` (built from
  `CallAttempt` + `CustomerIntent` only, never `CallTranscript`, per spec §0.7; defensively
  re-runs `redact()` on its own output before persisting), `get_claim_delay_flag` (thin
  `session.get(MotorClaim, claim_id)` lookup for the DISSATISFIED fix),
  `count_recent_attempts_activity` (thin wrapper), `record_runtime_failure_event` (a new
  public wrapper around the existing private `_record_runtime_failure`,
  `calls/activities.py:69-83`, needed from `voice/pipeline.py` per spec §5.3)
- `ALL_CALLS_ACTIVITIES` (`calls/activities.py:536-554`) gains all new entries — `worker.py`
  needs no new import, since it already imports the list, not individual names
- **Verify no new activity body calls `activity.info()`/`activity.heartbeat()`** — a quick
  grep before the batch is marked done. This matters concretely: `persist_transcript_turn`,
  `record_sentiment_event`, and `record_latency_sample` will all be called *directly* from
  `voice/pipeline.py` outside a real Temporal activity execution context (Batch 10), the
  exact pattern `record_audit_event` already uses successfully from `_tag_if_adversarial`
  (`pipeline.py:191-202`) — safe only because none of these functions touch activity-context
  APIs, and that must hold for the new ones too, not just be assumed from the spec text
- **Tests:** `tests/integration/test_phase3_transcript_pipeline_e2e.py` driving
  `persist_transcript_turn` directly with a fabricated Emirates ID, asserting no raw digits
  survive into `CallTranscript.redacted_text` and a matching `PiiRedactionEvent` row exists;
  `generate_call_summary` tested against Batch 6's fake adapter, asserting a forced failure
  surfaces cleanly from the activity itself rather than being silently swallowed (the
  workflow decides best-effort semantics in Batch 8, but the activity must not hide errors)

### Batch 8 — `calls/workflows.py` wiring (highest-risk batch — its own reviewable unit)
This batch **edits working, tested code**. Each of the five changes below is treated as an
independent diff, with the full existing Phase 1+2 e2e suite re-run after each one, not just
once at the end of the batch:

1. **DISSATISFIED branch fix (spec §0.8/§3.7):** insert the `get_claim_delay_flag` activity
   call; `action_code = "CLAIM_DELAY_ESCALATION" if claim.delay_flag else "CLAIMS_TEAM_QUERY"`.
   `calls/disposition.py::resolve_disposition` only ever reads `ctx.action_created: bool`,
   never the actual action-code string, so the one existing e2e test for this branch stays
   green regardless of which code is chosen — **it does not prove the fix**. The new
   `test_dissatisfied_branch_delay_gate.py` (both `delay_flag=True` and `delay_flag=False`
   cases) is what actually proves it, and the existing e2e test's seeded claim needs its
   `delay_flag` made explicit rather than left to whatever its default `claim_stage`
   produces. (Demo seed data already includes a `delay_flag=True` row —
   `scripts/seed_demo_data.py:124` — confirming this is exercisable against real data too.)
2. **Four `_record_intent` call sites** — one shared helper, called immediately after each
   `_wait_for_signal()` result, before the existing branch-dispatch chain, across
   `_run_right_party_check`/`_run_authentication`/`_run_otp_challenge`/
   `_run_status_and_follow_up`. These four call sites have near-identical but not identical
   loop shapes — verify none of the four accidentally reorders an existing
   `if signal.intent == ...` check relative to the loop's continuation path.
3. **REPEATED_CONTACT check in `run()`**, right after `create_call_attempt` — a new
   `execute_activity` call at the very start of the workflow, before any existing branch.
   New `REPEATED_CONTACT_WINDOW_DAYS`/`REPEATED_CONTACT_THRESHOLD` constants in
   `calls/constants.py` (plain module constants, not a new `BaseSettings` subclass, per the
   spec's own reasoning — two values don't justify a new settings class).
4. **`self._attempted_at` + `duration_seconds` fix** — one new `__init__` field, set at the
   top of `run()`, consumed in `_finalize()`'s existing `FinalizeOutcomeInput(...)`
   construction (the field already exists end-to-end per `calls/activities.py:212` and
   `calls/service.py:73` — only the call site was missing it).
5. **`generate_call_summary` call in `_finalize()`**, after the existing
   `finalize_outcome`/`record_audit_event` calls, deliberately best-effort with no branch on
   failure — a missing `CallSummary` must never block or delay the workflow's own
   finalization.

**Replay-determinism note:** items 3 and 5 insert new `execute_activity` calls at points no
historical `CallSessionWorkflow` execution's event history previously contained.
`MAX_CALL_SESSION_SECONDS = 900` (`calls/constants.py`) bounds the exposure window to at most
15 minutes of in-flight executions at deploy time. This repo has no existing
`workflow.patched()` usage anywhere (confirmed by search) — no established versioning
convention to reuse yet. Given the demo-tier, non-production-pilot status of this phase,
**accept the 15-minute window explicitly rather than introducing `workflow.patched()`** —
document this decision in the workflow's own module docstring so it's a conscious choice
Phase 5/6 can revisit, not a silently-discovered gap.

- **Tests:** `test_dissatisfied_branch_delay_gate.py`, `test_call_duration_populated.py`
  (full scripted run, `duration_seconds` non-`None`, roughly matches simulated elapsed
  time), a REPEATED_CONTACT integration test (seed ≥ threshold prior attempts, assert the
  call-start `SentimentEvent` row exists and no other branch's behavior changed), a
  summary-generation-failure test (force Batch 6's fake adapter to raise, assert
  `CallSessionOutput` still returns normally)
- **Verify:** the *entire* existing Phase 1 + Phase 2 e2e suites pass unmodified except where
  a test's own seed data needed an explicit `delay_flag` — that's the signal this batch
  didn't silently change behavior elsewhere

### Batch 9 — `RuntimeFailureEvent` STT/LLM/TTS extension (spec §5.3)
- Isolated on purpose from Batch 10's larger tap rewrite: only needs `record_runtime_
  failure_event` (built in Batch 7) called from `voice/pipeline.py`'s error handling around
  the STT/LLM/TTS service calls
- Requires confirming Pipecat's actual `ErrorFrame`/exception types against the pinned
  `pipecat-ai==1.8.1` at implementation time — the spec explicitly hedges this the same way
  the Phase 2 spec hedged Pipecat internals it hadn't pinned down; kept its own small batch
  precisely so a wrong guess here doesn't entangle Batch 10
- **Test:** fault-injection unit test simulating an STT/LLM/TTS service exception, asserting
  a `RuntimeFailureEvent` row with the correct `component`

### Batch 10 — `voice/pipeline.py` tap changes (transcript, sentiment, AI-turn, latency)
- Depends on Batch 7 (activities), Batch 2 (`classify_sentiment`), and functionally on Batch
  8 (the DELAY_DISSATISFACTION safety-net signal is only meaningful once the workflow
  actually gates on `delay_flag`)
- `CallPipelineContext` gains `turn_index`; `_persist_turn`, `_tag_sentiment` (+ the
  DELAY_DISSATISFACTION safety-net signal into the existing `customer_utterance` handler —
  explicitly a safety net alongside the LLM's own conversational handling, never a
  replacement for it), the symmetric AI-turn tap, and the latency tap
- **Decide and document explicitly in code, not just the spec:** `turn_index` is one shared,
  monotonically-increasing counter across *both* CUSTOMER and AI-authored rows, not a
  per-speaker counter — required for `reporting/service.py`'s "initial sentiment = row with
  `MIN(turn_index)`" query (§11 below) to be meaningful; a future "fix" toward a per-speaker
  counter would silently break that query, so the reasoning needs to live next to the field,
  not only in the spec
- Same "confirm against the pinned Pipecat version" caveat as Batch 9 applies to the AI-turn
  text frame type and the end-of-speech/first-audio timestamps for the latency tap — no CI
  coverage possible for the frame-plumbing itself; the Batch 12 manual smoke test is what
  catches a wrong guess here
- **Test:** unit coverage against a fake `FrameProcessor` harness for `_persist_turn`/
  `_tag_sentiment`'s logic in isolation from real Pipecat frames; the frame-plumbing itself
  is smoke-tested only

### Batch 11 — `reporting/` package (router.py, service.py, schemas.py) + `main.py`
- Sequenced last among new-code batches deliberately: it's the one thing that needs every
  fact type (transcript/sentiment/latency/intent/summary) actually populated to be
  meaningfully verifiable, not just importable
- 6 GET endpoints (`operations-overview`, `outcome-funnel`, `no-answer-analytics`,
  `status-analytics`, `customer-experience`, `escalation-analytics`); `since`/`until`
  required, no default; no auth dependency (consistent with every other route today)
- **Call out explicitly — the one query shaped differently from every other metric:**
  "concurrent-call conflicts prevented" queries `AuditEvent.reason_code ==
  'CONCURRENT_CALL_CONFLICT'`, not `CallAttempt.disposition_code` — confirmed reading
  `campaigns/workflows.py::_finalize_concurrent_conflict`, which never creates a
  `CallAttempt` row at all
- Confirm spec §0.10's honestly-zero metrics (fraud/SIU referrals, silent-call failure rate,
  rejected/unreachable/invalid-contact-number counts) really do return `0` from real queries
  against real, currently-empty result sets — not a hardcoded placeholder
- **Test:** `test_phase3_reporting_queries_e2e.py` — seed `CallAttempt`/`SentimentEvent`/
  `CallLatencySample`/`AuditEvent` rows directly, hit all 6 endpoints, assert against
  hand-computed expected numbers — this is what proves the query map is actually correct,
  not just plausible-looking SQL
- **Verify:** missing `since`/`until` returns 422, not a silent default; `reporting_router`
  registered in `main.py` alongside the existing four routers

### Batch 12 — CI/governance additions + final regression + manual smoke test
- `tests/fixtures/bad_transcript_persistence.py` + `tests/unit/test_no_unredacted_
  transcript_writes.py` (grep-based enforcement that every real call site of
  `record_transcript_turn` in `src/` passes through `redact()`'s result first) — sequenced
  last since it greps over call sites written in Batches 7 and 10
- No new linter script needed — confirmed the two existing `check_tool_allowlist.py`/
  `check_no_raw_prompt_concat.py` scripts already scan `src/voice/**/*.py` generically and
  this phase adds no new raw-prompt-construction call site outside that coverage
- Confirm `backend/README` documents the `python -m spacy download en_core_web_sm` step for
  any fresh environment (Batch 2's requirements addition alone won't install the model)
- Full regression: entire Phase 1 + Phase 2 + Phase 3 suites together
- **Live manual smoke test (not CI):** a full demo call over real Whisper/Piper/Gemini,
  followed by manually inspecting the persisted `call_transcript` rows for that call — the
  phase file's own Notes section calls this "cheap now, expensive to discover missing during
  Phase 5"
- End-of-phase acceptance against `.claude/specs/phase-3-backend-spec.md` §10's exit-criteria
  traceability table

---

## Key risks & mitigations (condensed)

| # | Risk | Mitigation |
|---|---|---|
| 1 | `persist_transcript_turn`'s spec sketch wraps `record_redaction_events()` (which self-commits via `idempotent()`) inside an outer `session.begin()` — a documented contract violation | Drop the outer `session.begin()`; commit `CallTranscript` directly, then call `record_redaction_events()` separately (Correction 1, Batch 3/7) |
| 2 | `CallTranscript` has no uniqueness protection — a duplicated direct call (reconnect, race) could silently double-write a turn | Unique constraint on `(call_attempt_id, turn_index, speaker)` (Correction 2, Batch 1) |
| 3 | New `execute_activity` call sites in `run()`/`_finalize()`/the DISSATISFIED branch risk non-deterministic replay for in-flight `CallSessionWorkflow` executions across the deploy boundary | `MAX_CALL_SESSION_SECONDS=900` bounds exposure to 15 minutes; no `workflow.patched()` convention exists yet — accept the window explicitly and document it (Batch 8) |
| 4 | The DISSATISFIED-branch delay-flag fix doesn't change `resolve_disposition`'s output, so the one existing e2e test for this branch stays green without exercising the fix at all | New `test_dissatisfied_branch_delay_gate.py` with both `delay_flag` values is what actually proves it; existing e2e seed data needs an explicit `delay_flag` (Batch 8) |
| 5 | Direct (non-workflow) activity-function calls from `voice/pipeline.py` could break if a new activity body touches `activity.info()`/`activity.heartbeat()` | Verified safe by existing precedent (`record_audit_event`); grep-check the 3 new direct-call activities before Batch 7 is marked done |
| 6 | Presidio/spaCy adds a heavy dependency plus a separate non-pip model-download step, easy to miss in a fresh environment or CI image | Document in `backend/README` explicitly, verified again in Batch 12; confirm real version pins at implementation time rather than trusting unverified spec numbers (Batch 2) |
| 7 | `generate_call_summary`'s Gemini call is out-of-band and can't run in CI under the "no real LLM in CI" discipline | Monkeypatchable adapter factory, mirroring `get_otp_delivery_adapter` (Batch 6) |
| 8 | A shared global `turn_index` counter across CUSTOMER/AI rows could later be "fixed" into a per-speaker counter, silently breaking `reporting/service.py`'s `MIN(turn_index)` query | Document the design decision in code at the point `turn_index` is defined (Batch 10) |
| 9 | Both the STT/LLM/TTS `RuntimeFailureEvent` extension and the AI-turn/latency taps depend on Pipecat frame/exception types unconfirmed until implementation time | Two separate, narrowly-scoped batches (9, 10) so a wrong guess doesn't entangle the rest of the phase; covered by the mandatory manual smoke test, not CI (Batch 12) |
| 10 | New FK-less tables (`pii_redaction_event` and, per this repo's explicit-over-implicit convention, all 6 new tables) must be added to `tests/conftest.py`'s hardcoded TRUNCATE list or rows silently accumulate across test runs | Explicit Batch 1 checklist item, not left to "CASCADE will handle it" |

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

End-of-phase acceptance is the traceability table in
`.claude/specs/phase-3-backend-spec.md` §10 — every row verified against real
`CallAttempt`/`SentimentEvent`/`CallLatencySample`/`CallSummary`/`PiiRedactionEvent` rows and
live `reporting/` endpoint responses (not log inspection), matching
`phases/phase-3-operational-intelligence.md`'s own exit criteria wording — plus the Batch 12
manual smoke test's inspection of real persisted transcripts for redaction correctness.
