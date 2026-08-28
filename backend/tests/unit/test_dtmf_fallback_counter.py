"""voice/dtmf.py — spec §8.9. Pure-function tests, no Pipecat/DB/Temporal involved (by
design — see the module's own docstring)."""

from src.voice.dtmf import (
    fallback_prompt,
    register_low_confidence_turn,
    reset_counter,
    resolve_dtmf_action,
)


def test_counter_increments_per_call_independently():
    assert register_low_confidence_turn("CALL-A") == 1
    assert register_low_confidence_turn("CALL-A") == 2
    assert register_low_confidence_turn("CALL-B") == 1  # independent per call_id
    reset_counter("CALL-A")
    reset_counter("CALL-B")


def test_reset_clears_the_count_for_that_call_only():
    register_low_confidence_turn("CALL-C")
    register_low_confidence_turn("CALL-C")
    register_low_confidence_turn("CALL-D")
    reset_counter("CALL-C")
    assert register_low_confidence_turn("CALL-C") == 1
    assert register_low_confidence_turn("CALL-D") == 2  # untouched by CALL-C's reset
    reset_counter("CALL-D")


def test_reset_on_unknown_call_id_is_a_no_op():
    reset_counter("CALL-NEVER-SEEN")  # must not raise


def test_resolve_dtmf_action_mapping():
    """spec §8.9's minimum mapping: 1 -> CALLBACK, 2 -> HUMAN, anything else -> HUMAN (this
    demo-tier policy skips the "repeat once" step and routes directly, per dtmf.py's own
    documented rationale)."""
    assert resolve_dtmf_action("1") == "CALLBACK"
    assert resolve_dtmf_action("2") == "HUMAN"
    assert resolve_dtmf_action("9") == "HUMAN"
    assert resolve_dtmf_action(None) == "HUMAN"
    assert resolve_dtmf_action("") == "HUMAN"


def test_fallback_prompt_is_deterministic_and_language_aware():
    assert "press 1" in fallback_prompt("en")
    assert "press 2" in fallback_prompt("en")
    assert fallback_prompt("ar") != fallback_prompt("en")
    assert "1" in fallback_prompt("ar")  # digit itself, not translated
