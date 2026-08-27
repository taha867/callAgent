# Phase 2 — Conversation Layer

**Status:** Not Started
**Depends on:** [Phase 1 — Deterministic Core](./phase-1-deterministic-core.md)
**Spec references:** §35 Phase 2, §2.2 (Conversational AI Layer), §2.2.1 (Latency/Dead-Air),
§2.2.2 (Prompt Injection Defense), §2.2.3 (Language/Code-Switching), §8.9 (DTMF Fallback),
Demo 1 & Demo 4 (§29)
**Code-shape references:** `CLAUDE.md` §2.7 (Voice pipeline & vendor adapters)
**Tech stack:** `IMPLEMENTATION_PLAN.md` §1 — demo-tier: self-hosted Whisper/Groq (STT),
Piper (TTS), Gemini/Groq free tier (LLM), browser audio (telephony)

## Goal

Replace the Phase 1 text-harness stub with real streaming voice — **without touching Phase
1's control logic**. If this phase requires editing the state machine, eligibility rules,
or auth logic from Phase 1, that's a signal Phase 1 wasn't actually decoupled from voice.

## Tasks

- [ ] Wire the Pipecat pipeline: audio in (demo: browser mic; production: telephony audio)
      → STT → intent/fact extraction via LLM tool-use → deterministic engine decides next
      state → LLM phrases the approved response (grounded only in data the engine hands it)
      → streaming TTS → audio out.
- [ ] Build STT/LLM/TTS/telephony as swappable adapters (`src/voice/adapters/*/base.py`
      `Protocol` + provider implementations, per `CLAUDE.md` §2.7) from the start — the
      demo-vendor → production-vendor swap in Phase 6 must touch config only, never this
      pipeline's code.
- [ ] Enforce spec §2.2.2 mechanically: the LLM only ever receives (a) the current approved
      facts the engine selected and (b) the caller's latest utterance — never raw
      system-prompt concatenation of caller text, never direct tool execution without
      server-side authorization. (This should already be testable via the Phase 0 CI
      linter/allow-list — confirm it actually catches a violation here, not just in theory.)
- [ ] Barge-in / interruption handling via Pipecat's native support; verify TTS stops/ducks
      immediately on caller speech.
- [ ] Latency telemetry (spec §2.2.1): OpenTelemetry spans per hop (STT, orchestration/LLM,
      backend/tool, TTS-first-byte, total turn), dashboards for P50/P95/P99; deterministic
      holding phrase when `BACKEND_SOFT_WAIT_MS` is exceeded — never an LLM-improvised
      filler.
- [ ] English conversation, then Arabic, then mixed/code-switching (spec §2.2.3) — build
      and test **sequentially, not simultaneously**; bilingual QA compounds fast if done in
      parallel.
- [ ] Adversarial input tagging (`ADVERSARIAL_INPUT_DETECTED`) as a cheap classifier
      (`src/voice/guard.py`) feeding a *signal*, never a state transition, into the
      deterministic engine (spec §2.2.2 rule 5).
- [ ] DTMF fallback (spec §8.9) after 3 consecutive low-STT-confidence turns
      (`MAX_CONSECUTIVE_LOW_STT_TURNS = 3`).

## Exit Criteria

- [ ] **Demo 1 — Successful Status Update** (spec §29) runs live end-to-end over the
      browser-audio demo transport: customer answers → right party confirmed →
      authentication succeeds → repair status delivered → customer asks a simple question →
      AI answers from claim data → summary → close.
- [ ] **Demo 4 — Authentication Failure** (spec §29) runs live end-to-end: right party
      confirmed → verification attempt 1 fails → alternate verification attempted →
      attempt 2 fails → AI refuses disclosure → official support option → close.
- [ ] Both demos pass in **both English and Arabic**.

## Notes

The free-tier/self-hosted vendors used here (per `IMPLEMENTATION_PLAN.md`'s cost strategy)
are good enough to prove the pipeline shape and demo the product — they are **not** the
vendors whose adversarial-resistance gets hardened in Phase 4/5. Don't let a clean Phase 2
demo create false confidence about jailbreak-resistance; that gets re-verified against
Claude specifically before production (see Phase 6).

---
**Previous:** [Phase 1 — Deterministic Core](./phase-1-deterministic-core.md)
**Next:** [Phase 3 — Operational Intelligence](./phase-3-operational-intelligence.md)
