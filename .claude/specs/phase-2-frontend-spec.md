# Phase 2 — Frontend Engineering Spec (Conversation Layer)

**Status:** Draft — scope decision, no build queued
**Derived from:** `.claude/specs/phase-2-backend-spec.md` (the actual, as-committed Phase 2
backend, commit `2514289`) · `phases/phase-2-conversation-layer.md` · `CLAUDE.md` §1
(architecture overview — Shape A vs. Shape B) and §3 (frontend conventions) ·
`.claude/specs/phase-1-frontend-spec.md` (this phase's starting frontend code state)

**Purpose of this document:** every prior phase got a frontend spec that carved out a real
slice of work. This one exists to record, with the same rigor, **why Phase 2 carves out no
slice at all** — so that decision is a documented, checked conclusion instead of a silent
gap someone has to re-derive later. §0 is the actual content of this document; §1 is the
verification that backs it up; §2 says what does carry forward unchanged; §3 points at the
phase that picks this thread back up.

---

## 0. Design decision: Phase 2 ships zero frontend changes

`phase-2-conversation-layer.md`'s task list is entirely about `backend/src/voice/` —
wiring Pipecat, STT/LLM/TTS/telephony adapters, the tool-dispatch → Temporal signal bridge,
DTMF fallback, adversarial-input tagging, latency telemetry. None of it is dashboard work,
and the backend spec says so explicitly in its own §17: *"Ops-dashboard authentication,
frontend work of any kind — unchanged from Phase 1's deferral; nothing in `frontend/`
changes in this phase."* This document's job is to confirm that statement against the
actual committed code (not just trust the plan), because `phase-1-frontend-spec.md` §0.2
already showed once that a backend spec's plan and a backend phase's as-shipped code can
diverge — that check is repeated below rather than assumed.

This is a direct consequence of `CLAUDE.md` §1's architecture split, not an oversight:

> "The frontend never talks to Temporal, the telephony/voice pipeline, or the STT/LLM/TTS
> vendors directly — it only ever sees the backend's REST API and (for live-call
> monitoring) a read-only event stream the backend exposes."

Phase 2 builds the live-call side of that boundary (`voice_server.py`, a Pipecat process
that is a Temporal *client*, never a router — backend spec §0.1). It does not build the
read-only event stream `CLAUDE.md` reserves for live-call monitoring, and it adds no new
route to `main.py`'s four existing routers (`claims`, `actions`, `calls`, `complaints`). A
dashboard screen has nothing new to call.

The one place Phase 2 touches data the dashboard could theoretically care about —
`CallSession.language` (backend spec §0.7, §10) — is not reachable from any endpoint:
`CallSession` has no router at all today (`GET /calls/{call_id}` returns `CallAttempt`, via
`CallAttemptRead`, which has no `language` field and never embeds a `CallSession`). Adding
that exposure would mean the frontend spec inventing a backend endpoint mid-document, which
is backwards — `CLAUDE.md`'s Shape A lifecycle starts with the router, not with the
dashboard deciding it wants a field. That stays out of scope here.

**Consequently, this phase produces no new `pages/`, `containers/`, `components/<domain>/`,
`hooks/`, `services/`, or `validations/` files, and no build task list.** The honest content
of a "Phase 2 frontend spec" is the verification in §1 and the forward-pointer in §3.

---

## 1. Verification — what was actually checked before concluding "no work"

Read directly from the Phase 2 backend commit (`2514289`), not inferred from the plan:

1. **`backend/src/main.py`'s registered routers are unchanged from Phase 1** — still exactly
   `claims`, `actions` (mounted under `/claims`), `calls`, `complaints`. No `voice` router,
   no campaigns/telephony/customers router landed either (those were already absent per
   `phase-1-frontend-spec.md` §0.2 and remain absent).
2. **`calls/router.py` is untouched** — `GET /calls/{call_id}`, `GET /calls/{call_id}/outcome`,
   and `POST /calls` are the same three routes `phase-1-frontend-spec.md` was written
   against, returning the same `CallAttemptRead` shape. `CallAttemptRead` gained no fields.
3. **`CallSession` (the model `language` was added to) has no HTTP surface** — confirmed by
   grep: no `CallSessionRead` schema exists anywhere in `src/calls/schemas.py`, and no router
   constructs a response from a `CallSession` row. There is nothing for a frontend hook to
   query even if this spec wanted to expose the new column.
4. **`DispositionCode` gained no new enum values this phase** (backend spec §0.4 says this
   directly — `DTMF_FALLBACK_ACTIVATED`, `ADVERSARIAL_INPUT_DETECTED`,
   `SECURITY_POLICY_ESCALATION` all pre-date Phase 2). Cross-checked against
   `frontend/src/utils/constants.js` and `frontend/src/components/common/DispositionBadge.jsx`:
   both already list all three codes — `phase-1-frontend-spec.md`'s build already rendered
   against the full `DispositionCode` enum, not just Phase 1's reachable subset, so there is
   no badge/label gap for this phase to close either.
5. **The Phase 2 backend's own browser demo client is explicitly not frontend work** —
   backend spec §11: the WebRTC mic-capture page that talks to `voice_server.py`'s `/offer`
   endpoint "does not belong under `frontend/`... it ships as a static file served by
   `voice_server.py` itself." `CLAUDE.md`'s two-app boundary cuts both ways: the ops
   dashboard is an observer of the call system, and a live-call *participant* UI (which is
   what that demo page is) is not the dashboard's job either. Nothing under `frontend/` is
   the right place for it, and this spec does not claim it.

No gap surfaced. The conclusion in §0 holds against the real code, not just the plan.

---

## 2. What carries forward unchanged

Everything `phase-1-frontend-spec.md` built stays exactly as it is — `claims/`, `calls/`,
`actions/` (covering escalations), and `complaints/` on the frontend, the lookup-by-id
page shape (§0.3 of that spec), the `Idempotency-Key`-per-mount mutation pattern (§0.5), and
`ClaimStatusPanel`'s verification-level preview selector (§0.4). None of it references
anything Phase 2 changed. No regression check beyond §1's grep was needed because nothing
Phase 2 touched is on a path any existing frontend code reads.

---

## 3. What actually unblocks the next frontend phase

`phases/phase-3-operational-intelligence.md` is where this thread picks back up — its task
list is explicitly the first phase that needs new dashboard surface (`DashboardPage`,
`AnalyticsPage`, outcome funnel, no-answer/status/customer-experience analytics, per spec
§31), and its own exit criteria require every one of those metrics to come from real
Phase 1+2 data. Two Phase 2 artifacts are exactly what make that possible without faking
numbers:

- **The OpenTelemetry spans** `voice/telemetry.py` emits per turn (`STT`,
  `LLM_ORCHESTRATION`, `BACKEND_TOOL`, `TTS_FIRST_BYTE`, `TOTAL_TURN`) are what
  `LatencyMetricsPanel` (`CLAUDE.md` §3.3) will eventually chart as P50/P95/P99 — but that
  panel has no data source until a Phase 3 backend endpoint queries the metrics backend and
  exposes it over HTTP. Building `LatencyMetricsPanel` now would be wiring a component
  against a span exporter directly, which is exactly the "frontend never talks to the voice
  pipeline directly" boundary this document opened with.
- **`CallSession.language`** is what a future `CallEventLog`/transcript-adjacent view reads
  once Phase 3 builds `CallTranscript`/`CallSummary` and a router to serve them — again,
  gated on a backend endpoint that doesn't exist yet.

So the actionable next step is not "start Phase 3 frontend work now" — it's the same gating
condition `phase-1-frontend-spec.md` §0.2 already named: **wait for Phase 3's backend spec to
land the routes**, then write `phase-3-frontend-spec.md` against the real, as-shipped
endpoints, the same discipline this document and `phase-1-frontend-spec.md` both followed.

---
**Previous:** [`phase-1-frontend-spec.md`](./phase-1-frontend-spec.md)
**Next:** `phase-3-frontend-spec.md` (not yet written — depends on `phase-3-operational-intelligence.md`'s backend spec landing first)
