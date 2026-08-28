"""CompletionAdapter — a small, non-Pipecat "prompt in, structured JSON out" interface for
out-of-band LLM calls (conversation summarization, call-end sentiment) that run AFTER a call
ends, over already-persisted structured facts — not inside the live turn loop.

Deliberately separate from get_llm_service() (this package's __init__.py): that function
returns a Pipecat LLMService wired into the live streaming pipeline's LLMContext/tool-calling
machinery — the wrong shape for a single completion call, and reusing it would mean standing
up a throwaway Pipecat pipeline just to make one request. Same swappable-adapter shape as
every other adapter family (CLAUDE.md §2.7).
"""

from typing import Any, Protocol


class CompletionAdapter(Protocol):
    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]: ...
