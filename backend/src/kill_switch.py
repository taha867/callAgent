"""Global outbound kill switch — spec §39.

`assert_outbound_enabled()` is the one rule. Every outbound-triggering code path — a
FastAPI endpoint (via `require_outbound_enabled`) or a Temporal activity (calling
`assert_outbound_enabled` directly, since activities never see a `Request`) — goes through
this single function, never a re-implemented `if` at the call site. It reads
`settings.<FLAG>` at call time (not at import time), so a runtime flag flip — the entire
point of spec §39 ("stopping new calls without requiring an application deployment") —
actually takes effect, and so tests can `monkeypatch.setattr(settings, ...)`.
"""

from collections.abc import Callable
from typing import Literal

from fastapi import HTTPException, status

from src.config import settings
from src.exceptions import OutboundDisabledError

OutboundGate = Literal["campaign", "cli", "ai_automation"]

_GATE_FLAGS: dict[OutboundGate, str] = {
    "campaign": "CAMPAIGN_ENABLED",
    "cli": "CLI_ENABLED",
    "ai_automation": "AI_AUTOMATION_ENABLED",
}


def assert_outbound_enabled(*gates: OutboundGate) -> None:
    if not settings.GLOBAL_OUTBOUND_ENABLED:
        raise OutboundDisabledError("GLOBAL_OUTBOUND_ENABLED")
    for gate in gates:
        flag_name = _GATE_FLAGS[gate]
        if not getattr(settings, flag_name):
            raise OutboundDisabledError(flag_name)


def require_outbound_enabled(*gates: OutboundGate) -> Callable[[], None]:
    """FastAPI dependency factory: `Depends(require_outbound_enabled("campaign"))`.

    Must be a sync factory returning a sync callable — an `async def` factory would hand
    `Depends()` a coroutine object instead of a callable dependency.
    """

    def _dependency() -> None:
        try:
            assert_outbound_enabled(*gates)
        except OutboundDisabledError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    return _dependency


# Bare-name idiom for CLAUDE.md §2.2's `Depends(require_outbound_enabled)` — checks only
# the global flag, no per-gate flags.
require_global_outbound_enabled = require_outbound_enabled()
