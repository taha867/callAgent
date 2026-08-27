# Phase 5 — Security, Privacy & Compliance Hardening

**Status:** Not Started
**Depends on:** [Phase 4 — Demo Hardening & Governed Regression](./phase-4-demo-hardening.md)
**Spec references:** §39 (v1.3 Production-Hardening Deployment Gate, items 1–9 and 13),
§10 (Authentication Framework), §10.6 (Runtime Failure & Session Recovery), §19A
(Fraud/SIU Escalation), §28 (Legal Sensitivity/Legal Hold), §8.10 (Vulnerable-Customer
Protocol), §18.1 (Complaint SLA)

## Goal

Not detailed as its own phase in the spec's own §35 list, but explicitly required before
any live deployment (spec §39). This phase is sign-off-driven, not just code-driven — each
task below needs a named human owner, not just a passing test.

## Tasks

- [ ] **Security testing**: authentication, OTP, rate limits, session binding, replay
      protection — penetration test or a structured internal red-team pass.
- [ ] **Load testing**: concurrent calls, distributed locks (Temporal workflow-ID
      contention), STT/LLM/TTS latency under load, backend capacity.
- [ ] **Failure-injection testing** across telephony, STT, TTS, LLM, orchestration, DB, and
      core APIs — verify every `RUNTIME_COMPONENT_FAILURE` path in spec §10.6 degrades
      safely (deterministic fallback, never improvised content).
- [ ] **Privacy validation**: transcript/audio retention, redaction accuracy (re-verify
      Phase 3's redaction pipeline under adversarial input, not just cooperative), DSAR
      routing, restricted evidence storage for legal-hold/fraud cases.
- [ ] **Fraud/SIU sign-off** on the fraud-routing and evidence-preservation flow (spec
      §19A) — named reviewer, not just an engineering self-check.
- [ ] **Legal/Claims sign-off** on legal-sensitivity/legal-hold decisioning (spec §28's
      legal sensitivity section).
- [ ] **Consumer Protection/Compliance sign-off** on vulnerable-customer handling (spec
      §8.10).
- [ ] **Insurer-approved contact-hour/Ramadan/holiday/suppression policy** finalized and
      loaded into the contact-calendar service (was a stub since Phase 1 — this is where it
      becomes real data).
- [ ] **Complaint SLA policy values** approved by Compliance and the CBUAE-regulatory
      owner, with a named human owner for breach escalations (spec §18.1, §39 item 13).

## Exit Criteria

- [ ] Every item in spec §39 has a **named sign-off owner** and a passing test/review
      artifact attached to it — not just a checkbox ticked by engineering.
- [ ] A findings/remediation log exists for the security and failure-injection testing,
      with every finding either fixed or explicitly accepted (with an owner and reason) —
      not silently dropped.

## Notes

This phase is deliberately not code-shaped like the others — most of the work here is
coordinating with people outside engineering (Compliance, Legal, Fraud/SIU, Consumer
Protection, the CBUAE-regulatory owner) who weren't needed for Phases 0–4. Start scheduling
those reviews as early as Phase 3–4 wrap up, not after — sign-off calendars are usually the
actual critical path here, not the engineering work.

---
**Previous:** [Phase 4 — Demo Hardening & Governed Regression](./phase-4-demo-hardening.md)
**Next:** [Phase 6 — Production Readiness & Pilot](./phase-6-production-pilot.md)
