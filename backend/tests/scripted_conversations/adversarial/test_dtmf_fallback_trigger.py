"""AdversarialScenarioId.DTMF_FALLBACK_TRIGGERED — deduped from three raw checklist bullets
("STT uncertainty / low confidence", "Persistent low STT confidence -> DTMF fallback",
"Three consecutive low-STT turns -> DTMF fallback"), all the same mechanism:
voice/dtmf.py's per-call counter reaching MAX_CONSECUTIVE_LOW_STT_TURNS (3).

Pure unit test of the counter module itself — the workflow-level dtmf_fallback signal ->
DTMF_FALLBACK_ACTIVATED disposition is already covered by
tests/integration/test_phase2_pipeline_signal_bridge.py's
test_dtmf_fallback_signal_routes_to_callback/_to_human, so this test isn't duplicated here.
"""

from src.voice import dtmf
from src.voice.config import voice_settings


def test_counter_reaches_threshold_after_three_consecutive_low_confidence_turns():
    call_id = "CALL-DTMF-TEST-1"
    dtmf.reset_counter(call_id)
    assert voice_settings.MAX_CONSECUTIVE_LOW_STT_TURNS == 3

    counts = [dtmf.register_low_confidence_turn(call_id) for _ in range(3)]
    assert counts == [1, 2, 3]
    assert counts[-1] >= voice_settings.MAX_CONSECUTIVE_LOW_STT_TURNS

    dtmf.reset_counter(call_id)
    assert dtmf.register_low_confidence_turn(call_id) == 1  # a real transcription resets it


def test_resolve_dtmf_action_maps_1_to_callback_and_anything_else_to_human():
    assert dtmf.resolve_dtmf_action("1") == "CALLBACK"
    assert dtmf.resolve_dtmf_action("2") == "HUMAN"
    assert dtmf.resolve_dtmf_action(None) == "HUMAN"
