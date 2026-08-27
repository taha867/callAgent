# Insurance Outbound AI Call Center — Technology & Phase-Wise Implementation Plan

**Based on:** `Insurance_Outbound_AI_Call_Center_Motor_MVP_Developer_Spec_v1_3.md`
**Companion framework:** Judgment Compiler governance pattern (see §0 and Phase 4)
**Status:** DRAFT FOR DISCUSSION — not yet approved

---

## 0. How This Plan Reads the Spec

The spec is unusual for an "MVP" doc: it already separates **deterministic control** (state
machine, auth, disclosure, idempotency) from **generative conversation** (LLM phrasing,
intent extraction), and it already ends with a compiled rule corpus — Section 36's 36
"Non-Negotiable Engineering Rules." That is not incidental; it's the same idea described in
the Judgment Compiler article:

> Source that is human judgment (here: the compliance/security reasoning baked into the
> spec by its authors), paid for by rejections (here: every "must not," "never," "do not"
> in the spec); output that is machinery which rejects without a human (here: the
> deterministic workflow engine, allow-listed tool schemas, and CI gates).

Two consequences for how we build this:

1. **The LLM is never the source of truth for a decision.** It phrases, extracts, and
   classifies. Every state transition, disclosure, and write is arbitrated by code the LLM
   cannot influence except through structured, allow-listed tool calls.
2. **New failure patterns discovered during hardening (Phase 4) don't get fixed by editing
   a prompt.** The spec's own §36 was clearly built this way — every rule reads like a
   post-incident lesson. We continue that discipline explicitly: **the second time a
   conversation defect repeats in a different scenario, it gets compiled into a
   deterministic test/gate/rule before the ticket is closed**, not left as "the LLM should
   remember not to do that." This is cheap to do and prevents regression as the surface
   area grows across English/Arabic/adversarial/failure-injection testing.

---

## 1. Recommended Technology Stack

**Cost strategy:** the client demo must run at **$0 recurring spend**. Everywhere below,
the "Demo/POC" column is either self-hosted open source (genuinely free forever) or a
vendor's free tier (free up to a quota, not free at scale). The "Production (later)" column
is the paid swap-in once real customers/volume arrive. Every vendor-backed component
(telephony, STT, TTS, LLM) is used **behind a thin interface/adapter** from Phase 1 onward
specifically so that swap is a config change, not a rewrite — this was already the plan for
STT/TTS vendor choice; it now applies to all four.

| Layer | Demo/POC (Zero-Cost) | Production (Paid, later) | Notes |
|---|---|---|---|
| **Durable workflow / state machine** | **Temporal OSS**, self-hosted via docker-compose | Same (Temporal OSS self-hosted) or **Temporal Cloud** if the team doesn't want to operate it | Temporal OSS has no license cost at any scale — self-hosting is a legitimate permanent choice, not just a demo shortcut. Only move to Temporal Cloud if operating it becomes a burden, not because of cost. |
| **Real-time voice orchestration** | **Pipecat** (open source) | Same | Free at any scale, no swap needed. |
| **Telephony / SIP trunk & CLI** | **No real PSTN calls for the client demo** — run the pipeline over a browser mic/speaker (WebRTC/local-audio transport, which Pipecat supports natively) so the client hears and speaks to the agent live with **zero carrier cost**. If the client specifically wants to see a real phone ring, use Twilio's one-time free trial credit (~$15, enough for a handful of demo calls) — call this out as a *temporary* trial, not a cost-free production path. | UAE-licensed carrier trunk (Etisalat/du) or Twilio Elastic SIP Trunking, insurer-owned/authorized CLI, billed per real spec §4.1 | Be explicit with the client: **real PSTN calling is never $0** — every carrier bills per minute/number. There is no free production telephony option; this line item only gets deferred, not eliminated. |
| **STT** | **faster-whisper (Whisper large-v3)**, self-hosted, or **Groq's free-tier hosted Whisper API** (no local GPU needed, generous free rate limit) | **Deepgram Nova-3** (streaming, multilingual, code-switching) or **Azure Speech** | Self-hosted Whisper has no code-switching-aware streaming mode as polished as Deepgram's and is slower without a GPU — acceptable for a demo's call volume, not for production P95 latency targets in §2.2.1. Groq's free tier is the better zero-cost demo option if available (hosted, fast, no infra to run). |
| **TTS** | **Piper TTS** (self-hosted, real-time on CPU) for English; evaluate Piper/Coqui XTTS community Arabic voices for demo Arabic quality before committing | **ElevenLabs** (Flash/Turbo) or **Azure Neural TTS** (Gulf Arabic voices) | This is the biggest quality gap between free and paid — open-source TTS Arabic voices are noticeably less natural than ElevenLabs/Azure. Set the client's expectation that demo voice quality is a placeholder, not final production quality. |
| **Conversation LLM** | **Google Gemini API free tier** or **Groq free tier** (Llama 3.3 70B / Qwen2.5, function-calling capable) for the demo | **Claude (Sonnet)** for dialogue/tool-use, **Claude (Haiku)** for cheap classifiers | This is the one substitution to flag most carefully: the spec's hardest requirement (§2.2.2 — caller speech can *never* override deterministic control, resist "system override"/jailbreak phrasing) depends on the model's instruction-following discipline under adversarial pressure. Open-weight/free-tier models are measurably weaker at holding this line than Claude. Fine for a client demo script; **do not treat free-tier LLM adversarial-resistance results as representative of production behavior** — Phase 4/5 adversarial hardening should be re-run against Claude before any real deployment decision. |
| **Backend services / APIs** | Python (FastAPI) + **Pydantic** for request/response and inter-service validation, self-hosted | Same | Free at any scale, no swap needed. |
| **Database** | **PostgreSQL** + **Redis**, self-hosted via docker-compose | Same self-hosted, or managed (RDS/Cloud SQL) for HA/backup convenience once uptime matters | Free at any scale; managed hosting later buys operational convenience, not new capability. |
| **PII redaction** | **Microsoft Presidio** + custom regex/checksum validators, self-hosted | Same | Free at any scale, no swap needed. |
| **Feature flags / kill switch** | **Unleash OSS**, self-hosted (or skip it and use a plain Postgres flags table for the demo — even simpler) | Same, or Unleash if not already adopted | Free at any scale. |
| **Observability** | **Prometheus + Grafana**, self-hosted; **Sentry free tier** for error tracking | Same, or Sentry paid tier once event volume exceeds the free quota | OpenTelemetry itself is free regardless. |
| **Dashboard/admin UI** | **React 19** (Vite) + shadcn/ui, run locally or hosted on a free static-hosting tier (Vercel/Netlify free plan) | Same | Free at any scale, no swap needed. |
| **CI/CD & governance** | GitHub Actions (free minutes tier for a small private/public repo) | Same, or paid Actions minutes at high CI volume | Free at demo scale. |
| **Hosting for the demo itself** | Everything above can run **locally on a dev machine** for the live client demo (simplest, zero risk, zero cost) or on a permanently-free cloud tier (e.g., Oracle Cloud Always Free VM) if it needs to be reachable outside the room | Cloud region with UAE data-residency guarantees (Azure UAE North, AWS Bahrain, or local/G42-hosted) | Data residency is a real production requirement (spec implies UAE customer data) but not a demo blocker — synthetic demo data doesn't need to live in-region. |

**Migration checklist (build once, use later):** because every vendor-backed component
(telephony, STT, TTS, LLM) sits behind an interface from Phase 1 onward, "moving to paid"
in Phase 6 becomes: swap the adapter implementation, re-run the Phase 4 adversarial/demo-
journey regression suite against the new vendor, confirm the data-residency contract, and
go — not a rewrite of the state machine, dashboard, or governance layer.

---

## 2. Phase-Wise Implementation Plan

The spec's own §35 gives a 4-phase build order (workflow → conversation → operational
intelligence → demo hardening). This plan keeps that order — it's the right sequencing for
this product — and wraps it with a governance phase at the start and two production-facing
phases at the end that the spec explicitly calls for in §39 but leaves undetailed.

**Each phase now has its own file under `phases/`** — goal, task checklist, exit criteria,
and phase-specific notes — so implementation can proceed one phase at a time without
re-reading this whole document each time. This section is the index; flip the Status column
as work proceeds (`Not Started` → `In Progress` → `Done`) so the table stays a true at-a-
glance tracker.

| # | Phase | Status | File |
|---|---|---|---|
| 0 | Foundations & Governance Setup | Not Started | [`phases/phase-0-foundations.md`](./phases/phase-0-foundations.md) |
| 1 | Deterministic Core (spec §35 Phase 1) | Not Started | [`phases/phase-1-deterministic-core.md`](./phases/phase-1-deterministic-core.md) |
| 2 | Conversation Layer (spec §35 Phase 2) | Not Started | [`phases/phase-2-conversation-layer.md`](./phases/phase-2-conversation-layer.md) |
| 3 | Operational Intelligence (spec §35 Phase 3) | Not Started | [`phases/phase-3-operational-intelligence.md`](./phases/phase-3-operational-intelligence.md) |
| 4 | Demo Hardening & Governed Regression (spec §35 Phase 4 + Judgment Compiler discipline) | Not Started | [`phases/phase-4-demo-hardening.md`](./phases/phase-4-demo-hardening.md) |
| 5 | Security, Privacy & Compliance Hardening (spec §39 items 1–9, 13) | Not Started | [`phases/phase-5-security-compliance.md`](./phases/phase-5-security-compliance.md) |
| 6 | Production Readiness & Pilot | Not Started | [`phases/phase-6-production-pilot.md`](./phases/phase-6-production-pilot.md) |
| 7 | Post-MVP: Intelligence Layer (spec §33) | Not Started | [`phases/phase-7-intelligence-layer.md`](./phases/phase-7-intelligence-layer.md) |

Each phase file links to the one before/after it, so once Phase 0 is opened, the whole
sequence can be worked through without coming back to this index — though it's worth
returning here to update Status as each phase completes.

---

## 3. Open Questions to Resolve Before Phase 0 Starts

1. **Telephony carrier** — which UAE trunk/CLI provider, and is Twilio Elastic SIP
   Trunking viable for the insurer, or does this require a direct Etisalat/du
   relationship?
2. **Data residency** — which cloud region is contractually acceptable to the insurer for
   Postgres/Redis/model calls (audio + transcripts are the sensitive payload)?
3. **STT/TTS vendor selection** — confirm Arabic Gulf-dialect quality with real sample
   audio before committing (Deepgram vs Azure, ElevenLabs vs Azure TTS) — this is a
   listening test, not a spec-reading exercise.
4. **LLM vendor/data-processing agreement** — confirm Anthropic API contractual terms meet
   the insurer's data handling requirements for regulated customer data.
5. **Team composition** — Phase 1 (deterministic core) and Phase 2 (voice/LLM) can
   proceed in parallel once Phase 0's shared schema exists; worth deciding if that's two
   workstreams or sequential given team size.

---

*This document is a discussion draft. Next step: open
[`phases/phase-0-foundations.md`](./phases/phase-0-foundations.md) and start working its
task checklist — that phase has no external dependencies and doesn't require the open
questions above to be resolved first, though items 1–4 should be answered before Phase 2
picks a real STT/TTS/LLM/telephony vendor to build the adapters against.*
