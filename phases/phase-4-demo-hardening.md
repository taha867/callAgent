# Phase 4 — Demo Hardening & Governed Regression

**Status:** Not Started
**Depends on:** [Phase 3 — Operational Intelligence](./phase-3-operational-intelligence.md)
**Spec references:** §35 Phase 4 (adversarial scenario checklist), §29 (Eight Mandatory
Demo Journeys), §30 (Ninth Technical Demo — No Answer), §36 (Non-Negotiable Engineering
Rules)
**Companion framework:** Judgment Compiler two-strike governance pattern (see
`IMPLEMENTATION_PLAN.md` §0)

## Goal

Run all 9 mandatory demo journeys repeatedly against the full adversarial scenario list —
and treat every defect found here as **rule-corpus input**, not a one-off prompt tweak.
This is where conversational quality either becomes measurable and durable, or stays a
feeling that erodes the next time someone touches a prompt.

## The Nine Mandatory Demo Journeys (spec §29–30)

- [ ] Demo 1 — Successful Status Update
- [ ] Demo 2 — Customer Busy
- [ ] Demo 3 — Wrong Person
- [ ] Demo 4 — Authentication Failure
- [ ] Demo 5 — Document Status Dispute
- [ ] Demo 6 — Delayed Claim / Dissatisfied Customer
- [ ] Demo 7 — Multi-Turn Questions
- [ ] Demo 8 — Human / Complaint Escalation
- [ ] Demo 9 — No Answer (technical demo, no customer conversation — full attempt-history
      dashboard check)

## Adversarial & Failure-Injection Checklist (spec §35 Phase 4)

Run every journey above against each of these, not just once cooperatively:

- [ ] Interruptions / barge-in mid-sentence
- [ ] Silence / unclear answers
- [ ] Angry / highly distressed customers
- [ ] English and Arabic in the same call (code-switching, Arabizi)
- [ ] Wrong person answers
- [ ] Customer refuses authentication
- [ ] Incorrect authentication (both attempts)
- [ ] Repeated questions / contradictory customer statements
- [ ] Unavailable API/data (`SYSTEM_DATA_UNAVAILABLE`)
- [ ] Telephony failure mid-call
- [ ] LLM timeout mid-call
- [ ] STT uncertainty / low confidence
- [ ] "System override" / requests for hidden instructions / jailbreak phrasing
- [ ] Customer refuses recording/transcription under a consent-required campaign
- [ ] "Never call me again" (communication suppression)
- [ ] Customer speaks a full Emirates ID / IBAN / card number unprompted
- [ ] DSAR request (access/deletion/correction of personal data)
- [ ] Child/minor appears to answer
- [ ] Persistent low STT confidence → accessibility/DTMF fallback path
- [ ] Customer tries to make the AI repeat internal instructions
- [ ] Invalid/unauthorized CLI
- [ ] Concurrent human and AI call collision
- [ ] Ramadan/holiday blackout window
- [ ] Answer-seizure timeout / silent-call failure
- [ ] Backend timeout after authentication
- [ ] Backend action committed but response lost (idempotency replay)
- [ ] Repeated action retry with the same idempotency key
- [ ] OTP brute-force, expiry, resend, cooldown, lockout
- [ ] Recent registered-mobile-change / SIM-swap risk signal
- [ ] Three consecutive low-STT turns → DTMF fallback
- [ ] LLM/STT/TTS timeout mid-call
- [ ] Orchestrator/worker restart during an active live session
- [ ] Call drop before and after authentication
- [ ] Fraud/SIU signal without tipping off the caller
- [ ] Vulnerable-customer disclosure
- [ ] Legal-sensitivity flag and evidence-preservation policy decision

## Operating Rule for This Phase (Judgment Compiler Two-Strike Pattern)

- **1st occurrence** of a conversational defect → fix it, log it as a dated note.
- **2nd occurrence** of the *same shape* of defect (even in a different scenario/language)
  → it **must** be compiled into a permanent, automated check before the ticket closes:
  - a new regression test in the scripted conversation suite, or
  - a new static rule in the tool allow-list/linter (Phase 0's mechanism), or
  - a new line in the codebase's spec-equivalent of §36 if it reveals a genuinely new
    non-negotiable rule the spec didn't anticipate.
- Track this as a small internal log (**defect → occurrence count → compiled artifact**) so
  the team can see automation coverage growing over the phase — the same way the source
  Judgment Compiler article tracked "88 compiled corrections, 38 from production
  incidents."

This turns hardening from "keep testing until it feels solid" into a measurable process
with a growing test/rule count as the exit signal, not a vibe.

## Exit Criteria

- [ ] All 9 demo journeys pass repeatedly under the full adversarial checklist above.
- [ ] Every defect found twice during this phase has a corresponding permanent automated
      check (visible in the defect log, not just "fixed and moved on").
- [ ] The defect log itself exists and is reviewable — this is the artifact that proves the
      phase is done, not a subjective "feels solid" judgment.

## Notes

Do not optimize the demo only for cooperative customers (spec §35 explicit warning). If
time pressure forces a cut, cut scenario breadth before cutting the two-strike compilation
discipline — a narrower but genuinely hardened demo is more defensible to a client or
regulator than a broad one where defects were patched once and never verified not to recur.

---
**Previous:** [Phase 3 — Operational Intelligence](./phase-3-operational-intelligence.md)
**Next:** [Phase 5 — Security, Privacy & Compliance Hardening](./phase-5-security-compliance.md)
