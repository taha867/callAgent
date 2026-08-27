# Phase 7 — Post-MVP: Intelligence Layer

**Status:** Not Started
**Depends on:** [Phase 6 — Production Readiness & Pilot](./phase-6-production-pilot.md)
**Spec references:** §33 (Future Intelligence Layer), §37 (Product Positioning)

## Goal

Only start this phase after Phase 6's pilot is stable and Compliance has signed off to
scale. This is the transition the spec describes in §37 — from an "AI outbound dialler" to
a "Customer Resolution Intelligence Engine."

## Scope (not a task checklist yet — this phase gets its own detailed plan once reached)

- Best-time-to-call prediction
- Probability of answer / right-party contact
- Preferred-language prediction
- Verification success probability
- Likely question category
- Probability of dissatisfaction / escalation / complaint
- Optimal communication channel selection
- Repeat-call likelihood

Conceptually:

```text
Customer + Claim Status + Historical Behaviour + Channel History
                           ↓
                    Prediction Layer
                           ↓
        Best Time / Channel / Conversation Strategy
                           ↓
                      AI Voice Agent
                           ↓
                 Outcome & Learning Data
```

## Notes

Not a Phase 0–6 concern to build — but **do not skip the early data collection this depends
on**. Spec §6.2's retry-variation data (attempted timestamp, weekday, time bucket, answer
result, historical customer answer patterns) should already be captured starting in Phase 1
as a side effect of the no-answer/retry scheduler, purely because it costs nothing extra to
log at write time and is expensive to reconstruct later if it wasn't captured. This phase's
job when it starts is to build the prediction layer on top of data that already exists, not
to first go figure out how to backfill it.

---
**Previous:** [Phase 6 — Production Readiness & Pilot](./phase-6-production-pilot.md)
