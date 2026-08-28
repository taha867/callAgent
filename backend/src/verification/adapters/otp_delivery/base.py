"""Same swappable-adapter shape as src/voice/adapters/* (CLAUDE.md §2.7) — a real SMS
vendor is a Phase 6 config change, not a rewrite of verification/service.py.
"""

from typing import Protocol


class OtpDeliveryAdapter(Protocol):
    async def send(self, *, phone_e164: str, code: str) -> None: ...
