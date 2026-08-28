"""DTMF fallback — spec §8.9. The per-call low-confidence-STT counter and the deterministic
fallback prompt/digit-mapping logic live here, deliberately free of any Pipecat import, so
they stay pure-function unit-testable; voice/pipeline.py (Phase 2 Batch 7) is what actually
plays the prompt (via a TTS adapter) and wires Pipecat's own DTMFAggregator FrameProcessor
to collect the digit, then calls this module's `resolve_dtmf_action` and signals
CallSessionWorkflow.dtmf_fallback with the result.

The counter is process-local, in-memory scratch state — the same category as spec §10.6.2's
"supports recovery within the same live telephony session only." A dropped/reconnected call
starts a brand-new CallSessionWorkflow execution (and a brand-new pipeline context) by
construction, per .claude/specs/phase-1-backend-spec.md §3.2 — there is nothing to recover
here across a restart, so this never needs to be persisted.
"""

from typing import Literal

# spec §8.9's exact wording.
FALLBACK_PROMPT_EN = (
    "I'm having trouble hearing you clearly. To schedule a callback, please press 1. "
    "To request a service agent, please press 2."
)
FALLBACK_PROMPT_AR = (
    "أواجه صعوبة في سماعك بوضوح. لجدولة معاودة الاتصال، يرجى الضغط على 1. "
    "لطلب التحدث مع موظف خدمة، يرجى الضغط على 2."
)

_counters: dict[str, int] = {}


def register_low_confidence_turn(call_id: str) -> int:
    """Returns the new consecutive-low-confidence count for this call."""
    _counters[call_id] = _counters.get(call_id, 0) + 1
    return _counters[call_id]


def reset_counter(call_id: str) -> None:
    _counters.pop(call_id, None)


def fallback_prompt(language: str) -> str:
    return FALLBACK_PROMPT_AR if language == "ar" else FALLBACK_PROMPT_EN


def resolve_dtmf_action(digit: str | None) -> Literal["CALLBACK", "HUMAN"]:
    """1 -> CALLBACK_REQUESTED, 2 -> HUMAN_REQUEST (spec §8.9's minimum mapping). No input,
    invalid input, or any other digit routes straight to HUMAN — spec §8.9 allows "repeat
    once, then safe close or human callback according to policy"; this demo-tier policy
    skips the repeat and routes directly, since a customer who can't be understood twice in
    a row is better served by a human immediately than by a third automated attempt."""
    if digit == "1":
        return "CALLBACK"
    return "HUMAN"
