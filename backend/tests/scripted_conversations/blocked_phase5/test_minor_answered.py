"""AdversarialScenarioId.MINOR_ANSWERED — blocked on Phase 5. DispositionCode.MINOR_ANSWERED
exists as an enum member (src/calls/constants.py) but is never produced by
resolve_disposition, and no detection code path exists anywhere in this codebase."""

import pytest


@pytest.mark.xfail(
    reason="Blocked on Phase 5 — no minor/child-detection code path exists; "
    "DispositionCode.MINOR_ANSWERED is enum-only with no producer.",
    strict=True,
)
def test_minor_detected_answering_routes_to_a_safe_outcome():
    from src.calls.disposition import resolve_disposition  # noqa: F401
    from src.risk import service  # noqa: F401 — src.risk doesn't exist yet
