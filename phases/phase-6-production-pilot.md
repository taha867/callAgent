# Phase 6 — Production Readiness & Pilot

**Status:** Not Started
**Depends on:** [Phase 5 — Security, Privacy & Compliance Hardening](./phase-5-security-compliance.md)
**Spec references:** §39 (kill switch, operational controls), §10.6.4 (Idempotency),
§2.2.2 (Prompt Injection Defense — re-verification)
**Tech stack:** `IMPLEMENTATION_PLAN.md` §1 — production-tier vendor swap

## Goal

Move from a hardened demo/staging system to a real, limited-volume pilot with real
telephony, real vendors, and real human fallback — without re-litigating anything Phases
0–5 already proved, only re-verifying what actually changed (the vendors).

## Tasks

- [ ] **Vendor swap from free/demo to paid production tier**:
  - [ ] STT → Deepgram Nova-3 / Azure Speech
  - [ ] TTS → ElevenLabs / Azure Neural TTS (Gulf Arabic voices)
  - [ ] LLM → Claude (Sonnet for dialogue, Haiku for classifiers)
  - [ ] Telephony → real UAE-approved CLI + carrier trunk (Etisalat/du or Twilio Elastic
        SIP Trunking with an insurer-authorized CLI)
  - [ ] Because every one of these sat behind an adapter since Phase 2
        (`src/voice/adapters/*`), this should be a config/credentials change per component —
        confirm that's actually true; if any swap requires touching pipeline code, that's a
        Phase 2 adapter-boundary bug to fix first.
- [ ] **Re-run the full Phase 4 adversarial/demo-journey regression suite against the new
      vendors before pilot** — do not assume behavior carries over, especially for the LLM
      swap: the free-tier model used for the demo is not the one whose jailbreak-resistance
      was hardened, so Claude's behavior against spec §2.2.2's adversarial scenarios must be
      verified fresh.
- [ ] Global outbound kill switch and per-campaign/per-CLI/per-automation flags live and
      tested against the production trunk (spec §39).
- [ ] Operational monitoring, alerting, incident response, and rollback runbooks written
      and rehearsed (not just documented).
- [ ] Reconciliation jobs for uncertain backend writes (`ACTION_WRITE_RESULT_UNKNOWN`) and
      stale distributed locks.
- [ ] Human fallback capacity and ownership confirmed for every escalation type the AI can
      create — a named team/person for each, not "someone will handle it."
- [ ] Small controlled pilot: limited campaign, limited volume, human QA reviewing a sample
      of calls before scaling attempt volume.

## Exit Criteria

- [ ] The pilot runs for an agreed period with **no spec §36 rule violations**.
- [ ] Latency/failure metrics (spec §2.2.1 P50/P95/P99, silent-call rate, backend/model
      failure rate) are within acceptable production thresholds, not just demo-scale
      thresholds.
- [ ] Compliance sign-off to scale beyond the pilot's limited volume/campaign.

## Notes

Treat the vendor swap and its regression re-run as the highest-risk step in this phase —
it's the one place where something genuinely new (Claude's behavior under adversarial
pressure, real carrier latency/jitter, real Arabic voice quality) meets a system that was
otherwise fully hardened against a different, cheaper stack. Budget real time for this
re-verification; don't treat it as a formality because "the demo already proved the
architecture works."

---
**Previous:** [Phase 5 — Security, Privacy & Compliance Hardening](./phase-5-security-compliance.md)
**Next:** [Phase 7 — Post-MVP: Intelligence Layer](./phase-7-intelligence-layer.md)
