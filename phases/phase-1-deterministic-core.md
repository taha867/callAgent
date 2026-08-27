# Phase 1 — Deterministic Core

**Status:** Not Started
**Depends on:** [Phase 0 — Foundations & Governance Setup](./phase-0-foundations.md)
**Spec references:** §35 Phase 1, §3 (Master Call State Machine), §4/§4.1 (Eligibility, CLI,
Voice Lock), §6 (No-Answer Protocol), §10 (Authentication Framework), §11–§13 (Status
Delivery), §18/§18.1 (Complaints & SLA), §23 (Structured Call Outcome), §26 (entities),
§38 (Developer Definition of Done)
**Code-shape references:** `CLAUDE.md` §2.1 (`customers/`, `claims/`, `campaigns/`,
`telephony/`, `calls/`, `verification/`, `actions/`, `complaints/`), §2.6 (Temporal)

## Goal

Everything that must **never** depend on the LLM, working end-to-end with a mocked voice
layer (text-in/text-out or scripted stub audio). If this phase is done correctly, Phase 2
only has to replace the stub input/output — none of this phase's decision logic changes
when real voice is wired in.

## Tasks

Build in this order — each step depends on the ones before it:

- [ ] **1. Data model** — all entities from spec §26 as SQLAlchemy models across the domain
      packages in `CLAUDE.md` §2.1, Postgres migrations for each.
- [ ] **2. Master call state machine** (spec §3) as a Temporal `CallSessionWorkflow` — one
      workflow per call attempt, `workflow_id` derived from `customer_id` so a second
      workflow for the same customer is rejected by Temporal (the distributed voice lock,
      spec §4.1 — no separate lock table needed).
- [ ] **3. Mock claims API/DB** (spec §27's `GET /claims/*` etc.) returning the structured
      claim status object (spec §12) — this is the Authoritative Data Layer (spec §2.3) the
      rest of the system reads from.
- [ ] **4. Call orchestrator**: eligibility checks (spec §4), CLI validation stub, contact-
      calendar stub (Ramadan/holiday table, real data loaded later in Phase 5).
- [ ] **5. Authentication service**: Level 0/1/2 logic (spec §10), OTP state machine with
      the exact configurable limits in §10.3.2 (`OTP_TTL_SECONDS`, `MAX_OTP_SENDS_PER_SESSION`,
      `MAX_OTP_ATTEMPTS`, `OTP_RESEND_COOLDOWN_SECONDS`, `OTP_LOCKOUT_MINUTES`),
      `MAX_AUTH_ATTEMPTS` handling (§10.4). `verification_level` lives on `CallSession`,
      never on `Customer` (spec §36 rule 28).
- [ ] **6. Status engine**: maps structured claim status → approved message key (spec §11,
      §13's 18 statuses) — template selection only, no free text generation yet.
- [ ] **7. Action/escalation/complaint service** with idempotency keys (spec §10.6.4, §18) —
      SLA timers (§18.1) as Temporal durable timers computed deterministically from
      insurer policy, never LLM-estimated.
- [ ] **8. Disposition engine** producing the outcome record (spec §23) for every attempt,
      including unsuccessful ones.
- [ ] **9. No-answer/retry scheduler** (spec §6) as a Temporal workflow with the 3-attempt
      policy and critical-status override (§6.9).
- [ ] **10. Runtime failure/recovery controller** (spec §10.6) — model this now even though
      there's no real LLM/STT/TTS yet, so Phase 2 integrates *into* a recovery framework
      instead of bolting one on later.

## Exit Criteria

- [ ] Every branch in spec §38's "Developer Definition of Done" diagram can be driven
      end-to-end through the state machine using a fake/text conversation harness:
      `NO ANSWER → retry`, `BUSY CUSTOMER → callback`, `WRONG PERSON → privacy-safe
      termination`, `AUTH FAILURE → disclosure blocked`, `NORMAL CUSTOMER → status
      delivered`, `QUESTION → grounded answer`, `DISPUTE → action created`,
      `DISSATISFACTION → escalation`, `COMPLAINT → complaint created`, `HUMAN REQUEST →
      transfer/callback`, `BACKEND FAILURE → deterministic recovery`, `OTP LIMIT →
      lockout`, `CALL DROP → auth expires`, `CONCURRENT CALL → AI attempt aborted`,
      `SUCCESS → summary + structured resolution`.
- [ ] Correct disposition codes and audit events are produced for every branch above —
      verified by reading the `AuditEvent`/outcome-record rows, not by eyeballing logs.
- [ ] All of this passes **before any real voice component exists** — the fake/text harness
      is the acceptance mechanism for this phase, not a temporary convenience.

## Notes

This is the largest phase and the one most worth resisting shortcuts on — a bug here (an
auth bypass, a non-idempotent write, a disposition code that's wrong) ships into every
later phase invisibly, because Phase 2 onward is verifying *conversation quality* against
this layer, not re-deriving its correctness. If Phase 1's exit criteria aren't genuinely met
end-to-end, don't start Phase 2 to "make progress" — it will only mean re-doing Phase 2's
integration work once Phase 1 gets fixed underneath it.

---
**Previous:** [Phase 0 — Foundations & Governance Setup](./phase-0-foundations.md)
**Next:** [Phase 2 — Conversation Layer](./phase-2-conversation-layer.md)
