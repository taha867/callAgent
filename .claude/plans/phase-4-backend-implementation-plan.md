# Phase 4 Backend — Implementation Plan (as executed)

## Context

`.claude/specs/phase-4-backend-spec.md` is the finalized engineering design for Phase 4
("Demo Hardening & Governed Regression") — a new `src/qa/` domain package that turns the
phase's Judgment Compiler two-strike governance rule (phases/phase-4-demo-hardening.md)
into DB-backed, dashboard-observable, CI-enforceable artifacts, plus a new
`tests/scripted_conversations/` regression suite that actually runs the 9 mandatory demo
journeys against the deduped adversarial checklist. Unlike Phases 1-3, this phase adds
almost no new *insurance-domain* concepts — it models the engineering process itself.

This plan was implemented in one continuous push, directly against the running
docker-compose stack (`callagent-backend-1`/`callagent-postgres-1`/`callagent-temporal-1`,
already up when this work started), verifying every piece live rather than only by code
review: every migration was actually applied, every new endpoint was actually curled, and
every new test file was actually run inside the container before being considered done.

**Execution reused the existing, running stack rather than a fresh environment** — this let
real defects surface immediately (see Correction 1 below) instead of being deferred to a
first real CI run.

---

## Corrections made during implementation (apply these, not the original plan's literal text)

1. **`PATCH /qa/defect-log/{entry_id}` — "transaction already begun" bug, found and fixed
   live.** The original plan's `router.py` sketch wrapped mutating routes in
   `async with db.begin():`. But `Depends(valid_defect_log_entry)` already touches the
   session (`db.get(...)`) before the route body runs, and SQLAlchemy's `AsyncSession`
   autobegins a transaction on first use — so a second explicit `db.begin()` in the route
   body raised `InvalidRequestError: A transaction is already begun on this Session`,
   caught by directly curling the endpoint. **Fix, applied uniformly to every mutating
   route:** call the service function, then `await db.commit()` explicitly — safe whether or
   not a transaction was already autobegun, unlike `db.begin()`.

2. **A genuine, previously-undiscovered production defect was found (not fixed) during
   adversarial testing — this is Phase 4 working as intended.**
   `tests/scripted_conversations/adversarial/test_system_data_unavailable.py` tried to
   exercise `calls/workflows.py::_run_status_and_follow_up`'s `backend_unavailable`
   fallback branch (claim not found -> `BACKEND_DATA_VERIFICATION_REQUEST` action). The
   fallback action itself inserts a `ClaimAction` row referencing `inp.claim_id` — but that
   column is a real FK to `motor_claim.id`, so when the claim genuinely doesn't exist (the
   exact condition this branch exists to handle), the fallback insert itself violates the FK
   constraint. With no `retry_policy` override on that `execute_activity` call, Temporal
   retries indefinitely until the workflow's 60s `execution_timeout` fires, raising
   `WorkflowFailureError` instead of resolving to `BACKEND_SYSTEM_FAILURE` as intended.
   - Logged via the live `qa/` API as defect `2dd6d559-0e48-40c4-bb7b-e89988082ef8`
     (shape key `backend-unavailable-fallback-action-fk-violation`).
   - A second occurrence was deliberately recorded (via `POST .../occurrences`) specifically
     to prove `scripts/ci/check_defect_log_two_strike.py` actually catches an uncompiled
     two-strike case (confirmed: exit code flipped 0 -> 1 -> 0 across create /
     second-occurrence / compile).
   - Marked `COMPILED` with `compiled_artifact_type=REGRESSION_TEST`, pointing at
     `test_system_data_unavailable.py` and `test_backend_timeout_post_auth.py` — both kept
     as `@pytest.mark.skip`-marked (not `xfail`, since a real fix would take ~70s to time
     out per run otherwise) regression tests documenting the exact defect, ready to be
     re-enabled once `calls/workflows.py`'s fallback-action branch is fixed to tolerate a
     genuinely-missing claim.
   - **Fixing `calls/workflows.py` itself was deliberately left out of scope** — it's
     production business logic outside "implement the qa/ domain + Phase 4 test suite," and
     per the phase's own two-strike rule, logging + a compiled regression artifact is the
     correct response to a found defect, not a silent, unreviewed production patch.

3. **`src/pagination.py`'s `Page[T]` uses PEP 695 generic syntax (`class Page[T](BaseModel)`),
   not `Generic[T]`** — `ruff check --fix` flagged `UP046` (this repo's ruff config already
   assumes Python 3.12 generics elsewhere); confirmed Pydantic 2.13.4 (already pinned)
   supports it, so this became the actual shipped code rather than a deferred cleanup.

4. **`temporal_env` had to be duplicated into `tests/scripted_conversations/conftest.py`**,
   not imported from `tests/integration/conftest.py` — pytest conftest fixtures apply to a
   directory's descendants, and `scripted_conversations/` is a *sibling* of `integration/`,
   not a descendant. This was flagged as a risk in the original plan and confirmed exactly
   as predicted on the first test run (`fixture 'temporal_env' not found`).

5. **`tests/scripted_conversations` connects to the real, persistent docker-compose Temporal
   server** (`temporal_env`'s first branch, `settings.TEMPORAL_HOST`), not an ephemeral
   per-run one — meaning workflow IDs (`f"call-session-{customer_id}"`) collide across
   separate pytest invocations that reuse the same seed suffix. Hit this directly
   (`WorkflowAlreadyStartedError`) when re-running a fixed test file with the same suffix
   twice; fixed by using a fresh suffix. Worth remembering for any future re-run of a single
   scripted-conversation test file in this shared dev environment.

6. **`LLM_PROVIDER` (not `VOICE_LLM_PROVIDER`) is the correct env var name** for
   `voice_settings.LLM_PROVIDER`, and no `src/voice/adapters/llm/claude.py` adapter exists
   yet (current valid values: `"gemini" | "groq_llm" | "openai"`) — both confirmed by direct
   inspection before writing `.github/workflows/phase4-claude-adversarial-rerun.yml`, which
   is written as a self-skipping job (checks for the adapter module before running) rather
   than assuming it exists.

---

## What shipped

- **`src/pagination.py`** (new) — `PaginationParams`/`Page[T]`, the first paginated list
  endpoint in this codebase.
- **`src/qa/`** (new domain package) — `constants.py` (`DemoJourneyId`, 28 canonical deduped
  `AdversarialScenarioId` members + `PHASE_5_BLOCKED_SCENARIOS`, `DefectStatus`,
  `CompiledArtifactType`), `models.py` (`DefectLogEntry`, `JourneyRunResult` — plain mutable
  rows, not insert-only), `schemas.py`, `exceptions.py`, `dependencies.py`, `service.py`,
  `router.py` — 8 endpoints under `/qa`, all manually curled and confirmed working,
  including the `compilation_required` computed-field round-trip.
- **Migration** `2026-08-29_add_qa_domain_tables.py` (down_revision `5df3ac54e432`, the true
  head confirmed via `docker exec ... alembic heads`) — applied cleanly.
- **`scripts/seed_demo_data.py`** — 2 synthetic `BusinessContactCalendar` rows (RAMADAN/
  BLACKOUT on 2026-09-05/06), idempotent-upsert verified by running the seed script twice.
- **`tests/scripted_conversations/`** — `conftest.py` (own `temporal_env`, `worker` fixture,
  `_seed_customer_and_claim`, `report_journey_run`), 9 `journeys/*` files (all 9 demo
  journeys, each disposition traced through `src/calls/disposition.py`'s actual match logic
  before being asserted, not guessed), 22 `adversarial/*` files covering all 24 non-blocked
  canonical scenarios (2 of those 24 — `SYSTEM_DATA_UNAVAILABLE`/`BACKEND_TIMEOUT_POST_AUTH`
  — are `skip`-marked pending the Correction 2 fix), 8 `blocked_phase5/*` `xfail(strict=True)`
  placeholders.
- **`scripts/ci/check_defect_log_two_strike.py`** — DB-backed (not AST-based like the other
  4 gate scripts), verified to actually flip exit code 0 -> 1 -> 0 against live data.
- **`.github/workflows/phase4-governance-check.yml`** and
  **`phase4-claude-adversarial-rerun.yml`** — both `workflow_dispatch`-only, YAML-validated.

## Verification performed

- `alembic upgrade head` — clean, both standalone and as part of the full migration chain.
- `ruff check .` (whole tree) and `mypy src` (whole tree) — both clean, zero new issues.
- All 4 pre-existing CI gate scripts re-run — unchanged, zero new violations.
- **`pytest tests/scripted_conversations`**: 45 passed, 2 skipped (known, logged, compiled
  defect), 8 xfailed (Phase 5 blocked) — 0 unexpected failures.
- **`pytest tests/unit tests/integration`** (the full pre-existing suite): 351 passed, 2
  skipped (pre-existing, unrelated) — confirms zero regressions from the `main.py`/
  `migrations/env.py` edits.
- Manually curled every `/qa` endpoint end-to-end, including the two-strike gate's full
  create -> second-occurrence -> compile -> re-check cycle.
- Confirmed a pre-existing, unrelated `NoReferencedTableError` traceback in
  `callagent-worker-1`'s logs (616 occurrences today) predates this work entirely — first
  occurrence timestamped at that container's boot, 16 hours before Phase 4 work started.
  Not touched; out of scope.

## Deferred / explicitly out of scope

- Fixing `calls/workflows.py`'s fallback-action FK-violation defect (Correction 2) —
  logged and compiled as a regression-test artifact, not fixed in production code.
- Building `src/voice/adapters/llm/claude.py` — the Claude adversarial re-run workflow
  self-skips until it exists.
- Real UAE Ramadan/public-holiday calendar data — only synthetic demo rows were added.
- `.claude/specs/phase-4-frontend-spec.md` — a separate, later implementation effort.
