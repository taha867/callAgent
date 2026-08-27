# Phase 0 — Foundations & Governance Setup

**Status:** Not Started
**Depends on:** nothing (first phase)
**Spec references:** §36 (Non-Negotiable Engineering Rules), §21 (AI Authority Matrix), §24/§25 (disposition/action codes), §32 (Explainable Operational Decisioning), §39 (kill switch)
**Code-shape references:** `CLAUDE.md` §2.1 (folder structure), §2.8 (config/kill-switch)

## Goal

Nothing dials yet. This phase makes "deterministic wins over generative" **executable**,
not just written down — every phase after this one builds on top of a rule corpus, a
shared schema, and an audit sink that already exist, instead of inventing them ad hoc under
deadline pressure later.

## Tasks

- [ ] Repo scaffolding: `backend/` (FastAPI + Temporal + Pipecat) and `frontend/` (React 19
      + Vite) per `CLAUDE.md` §2.1/§3.2–3.3, `docker-compose.yml` for local Postgres + Redis
      + Temporal OSS.
- [ ] One synthetic claims dataset (customers, policies, claims across all 18 statuses in
      spec §13) — this is what every later phase's tests run against.
- [ ] Stand up the **rule corpus**: turn spec §36 (36 non-negotiable rules) and §21 (AI
      Authority Matrix) into machine-checkable artifacts from day one:
  - [ ] `src/voice/tools.py` — the static allow-list of LLM tool schemas (empty/stub tools
        are fine now, the *mechanism* is what matters).
  - [ ] A CI linter/test that fails the build if a tool call appears anywhere in the
        codebase that isn't in that allow-list.
  - [ ] A test asserting the system/developer prompt is never rebuilt by concatenating raw
        caller text (spec §2.2.2 rule 2).
- [ ] Define the **structured disposition/action code enums** from spec §24/§25 as a shared
      schema (`src/*/constants.py` per domain, or one shared `src/constants.py` if that's
      cleaner at this size) — used by the workflow engine, event log, and dashboard alike.
      This becomes the contract every later phase writes against.
- [ ] Stand up the audit event pipeline skeleton: `audit.AuditEvent` model (insert-only, per
      `CLAUDE.md` §2.5) with the `decision`/`reason_code`/`policy_rule`/`action_taken` shape
      from spec §32 — before any real logic exists, so every phase after this logs into it
      instead of inventing ad hoc logging.
- [ ] `src/idempotency.py` — the `IdempotencyRecord` model + decorator/dependency every
      customer-impacting write will use starting Phase 1 (spec §10.6.4).
- [ ] Kill switch wired: `GLOBAL_OUTBOUND_ENABLED` / `CAMPAIGN_ENABLED` / `CLI_ENABLED` /
      `AI_AUTOMATION_ENABLED` in `src/config.py`, plus the `require_outbound_enabled`
      dependency — even though nothing dials yet, wire the check now so no later code path
      can be written that forgets it.
- [ ] `worker.py` stub that starts a Temporal worker with zero registered workflows (proves
      the process boots and connects to Temporal OSS before Phase 1 gives it real work).

## Exit Criteria

- [ ] An empty-but-typed workflow can be triggered end-to-end: fake call → fake disposition
      → `AuditEvent` row written → visible via a raw DB query.
- [ ] CI gates fail the build on any ungoverned tool call or a disposition/action code used
      that isn't in the shared enum.
- [ ] `docker-compose up` brings up Postgres, Redis, Temporal OSS, and an empty FastAPI app
      with one health-check route, from a clean checkout, with zero manual steps.

## Notes

This phase produces no user-visible behavior — resist the urge to skip it or rush it to get
to "something demoable." Every rule bent here (a tool call added without going through the
allow-list, an audit event skipped "just for now") is exactly the kind of shortcut spec §36
exists to prevent, and it's far cheaper to enforce the mechanism before there's any real
logic depending on it than to retrofit it in Phase 4.

---
**Next:** [Phase 1 — Deterministic Core](./phase-1-deterministic-core.md)
