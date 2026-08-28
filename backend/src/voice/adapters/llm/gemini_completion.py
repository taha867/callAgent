"""GeminiCompletionAdapter — the one CompletionAdapter implementation this phase ships,
using the `google-genai` SDK directly (already a transitive dependency of
pipecat-ai[google], confirmed installed — no new requirements/base.txt entry needed).
Reuses voice_settings.GEMINI_API_KEY, the same key the live pipeline's GoogleLLMService
already reads (voice/adapters/llm/__init__.py) — this is a second, independent client, not
a second credential.
"""

import json
from typing import Any

from google import genai
from google.genai import types


class GeminiCompletionAdapter:
    def __init__(self, *, api_key: str, model: str = "gemini-3.6-flash") -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
            ),
        )
        if response.text is None:
            # e.g. the response was blocked/empty — a real, if rare, failure mode; raising
            # here (rather than json.loads(None) blowing up with an unclear TypeError) is
            # what generate_call_summary's caller (calls/activities.py) expects to catch.
            raise ValueError("Gemini returned no text in its response")
        return json.loads(response.text)
