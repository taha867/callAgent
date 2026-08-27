# Phase 3 — Operational Intelligence

**Status:** Not Started
**Depends on:** [Phase 2 — Conversation Layer](./phase-2-conversation-layer.md)
**Spec references:** §35 Phase 3, §28 (Conversation Event Log / PII Redaction Pipeline),
§18 (Dissatisfaction Handling), §31 (MVP Dashboard Requirements)
**Code-shape references:** `CLAUDE.md` §2.1 (`privacy/`, `audit/`), §3.3 (`reporting/`
domain, `DashboardPage`, `AnalyticsPage`)

## Goal

Turn the raw events Phase 1–2 are already producing into the operational picture spec §31
requires — every dashboard metric must come from real data by the end of this phase, not
placeholders.

## Tasks

- [ ] Structured event logging finalized (spec §28) — redaction pipeline (Presidio +
      custom regex/checksum validators for Emirates ID, IBAN, UAE mobile formats) sitting
      between the raw STT buffer and the persisted transcript store, exactly as the
      pipeline diagram in §28 shows: `Audio → STT → Ephemeral Raw Buffer → PII Detection →
      Redaction/Tokenization → Approved Redacted Transcript Store → Summary + Structured
      Events`.
- [ ] Confirm the non-negotiable from `CLAUDE.md` §4 is actually true in code: the `calls/`
      transcript-persistence path **cannot** accept raw STT output directly, only the
      output of `privacy/`'s redaction pipeline.
- [ ] Conversation summaries (LLM-generated, but only summarizing engine-approved facts +
      caller intents already logged — never re-deriving new facts).
- [ ] Sentiment/dissatisfaction classification feeding spec §18's dissatisfaction signals
      (`NEGATIVE_SENTIMENT`, `DELAY_DISSATISFACTION`, `REPEATED_CONTACT`, etc.).
- [ ] Dashboard (React 19 + Vite): operations overview, outcome funnel, no-answer
      analytics, status analytics, customer experience analytics — all per spec §31.
- [ ] Attempt/escalation analytics views.

## Exit Criteria

- [ ] Every metric listed in spec §31 is populated from real Phase 1+2 data:
      - [ ] Operations Overview (calls scheduled/attempted, human answer rate, right-party
            contact rate, verification success rate, statuses delivered, AI-contained
            calls, actions/complaints/escalations/callbacks created, no-answer rate, avg
            call duration, P50/P95/P99 latency, silent-call/backend/model failure rates,
            DTMF fallback rate, concurrent-call conflicts prevented, dropped-call rate, OTP
            lockouts, fraud/SIU referrals, vulnerable-customer referrals).
      - [ ] Outcome Funnel (Scheduled → Attempted → Answered → Right Party → Authenticated
            → Status Delivered → Resolved by AI), with conversion shown at each stage.
      - [ ] No-Answer Analytics (by hour, by day, attempt number vs. answer rate, rejected/
            voicemail/unreachable counts, successful callbacks).
      - [ ] Status Analytics (question/escalation rate by status).
      - [ ] Customer Experience Analytics (initial/final sentiment, dissatisfaction rate,
            complaint rate, repeated-contact customers, calls requiring humans).
- [ ] None of the above are placeholder/mocked numbers — every chart traces to a real row
      in the database.

## Notes

This phase is where the redaction pipeline gets tested for real, not just designed —
run actual demo/hardening calls (from Phase 2) through it and manually inspect a sample of
persisted transcripts to confirm Emirates ID / IBAN / card numbers / OTPs never land in
long-term storage in the clear. This check is cheap now and expensive to discover missing
during Phase 5's privacy validation.

---
**Previous:** [Phase 2 — Conversation Layer](./phase-2-conversation-layer.md)
**Next:** [Phase 4 — Demo Hardening & Governed Regression](./phase-4-demo-hardening.md)
