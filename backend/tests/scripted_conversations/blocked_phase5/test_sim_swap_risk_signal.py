"""AdversarialScenarioId.SIM_SWAP_RISK_SIGNAL — blocked on Phase 5.
DispositionCode.HIGH_RISK_NUMBER_CHANGE_DETECTED is enum-only with no producer, and no
SIM-swap/registered-mobile-change signal source exists anywhere in this codebase yet."""

import pytest


@pytest.mark.xfail(
    reason="Blocked on Phase 5 — no SIM-swap/registered-mobile-change risk signal source "
    "exists yet; DispositionCode.HIGH_RISK_NUMBER_CHANGE_DETECTED is enum-only.",
    strict=True,
)
def test_a_recent_registered_mobile_change_triggers_a_risk_signal():
    from src.risk import service  # noqa: F401
