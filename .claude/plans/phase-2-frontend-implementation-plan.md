# Phase 2 Frontend — Implementation Plan

## Context

`.claude/specs/phase-2-frontend-spec.md` is the finalized engineering document for Phase 2
("Conversation Layer") on the frontend side. Unlike every prior phase's spec, its conclusion
is that **Phase 2 requires zero frontend code changes** — verified against the actual
committed Phase 2 backend (commit `2514289`), not just the phase plan's stated intent:

- `main.py` registers the same four routers as Phase 1 (`claims`, `actions`, `calls`,
  `complaints`) — nothing new for a screen to call.
- `CallSession.language` (the one new column Phase 2 added) has no HTTP surface at all —
  no `CallSessionRead` schema, no router builds a response from that model — so there is
  nothing for a frontend hook to query even if a screen wanted to show it.
- No new `DispositionCode` values were added this phase, and the ones Phase 2's workflow
  logic can now actually produce (`DTMF_FALLBACK_ACTIVATED`, `ADVERSARIAL_INPUT_DETECTED`,
  `SECURITY_POLICY_ESCALATION`) were already rendered by `frontend/src/utils/constants.js`
  and `frontend/src/components/common/DispositionBadge.jsx` since Phase 1 (that build
  already covered the full enum, not just Phase 1's reachable subset).
- The Phase 2 backend's own browser demo client (WebRTC mic capture talking to
  `voice_server.py`) is explicitly out of `frontend/`'s domain per the backend spec's own
  §11 and `CLAUDE.md`'s two-app boundary.

This plan exists to close out this phase the same way `.claude/plans/phase-1-backend-
implementation-plan.md` closed out Phase 1 backend — by persisting the decision as a durable
repo artifact in `.claude/plans/`, not leaving it as harness-internal state. There is no code
to sequence into batches; the "implementation" here is the plan document itself plus a final
confirmation check that nothing changed underfoot since the spec was written.

## Plan

**Step 1 — persist this plan as a project artifact.** Write this plan's content to
`.claude/plans/phase-2-frontend-implementation-plan.md` in the repo root, mirroring how
`.claude/plans/phase-1-backend-implementation-plan.md` is kept as a durable artifact rather
than just plan-mode scratch state.

**Step 2 — re-confirm the spec's verification still holds** (cheap, since nothing should
have changed since the spec was written minutes ago in this same session, but worth stating
as an explicit check rather than silently trusting a prior read):
- `git log --oneline -3` still shows `2514289 phase 2 backend` as the tip with a clean
  working tree (no new backend commits landed since the spec was drafted).
- `grep -rn "CallSessionRead" backend/src/calls/schemas.py` still returns nothing.
- `backend/src/main.py`'s `include_router` calls are still exactly `claims`, `actions`,
  `calls`, `complaints`.

**Step 3 — no `pages/`, `containers/`, `components/<domain>/`, `hooks/`, `services/`, or
`validations/` files are created or modified.** This is the deliverable of this plan: an
explicit, checked "no-op," not an omission.

**Step 4 — leave the forward pointer in place.** `.claude/specs/phase-2-frontend-spec.md`
§3 already names the unblocking condition for real frontend work to resume:
`phases/phase-3-operational-intelligence.md`'s backend spec landing new routes (dashboard
metrics, `CallTranscript`/`CallSummary` endpoints, a latency-metrics query surface). This
plan does not attempt to pre-build against those endpoints before they exist — the same
discipline `phase-1-frontend-spec.md` §0.2 already established when it found gaps between
`CLAUDE.md`'s full dashboard vision and what Phase 1's backend actually shipped.

## Verification

- After Step 1, confirm `.claude/plans/phase-2-frontend-implementation-plan.md` exists and
  its content matches this plan.
- Re-run the three checks in Step 2 and confirm each still holds.
- Confirm `git status` shows only the new plan file as a change (no accidental edits to
  `frontend/` or `backend/`).
