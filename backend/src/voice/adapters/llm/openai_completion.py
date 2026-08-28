"""OpenAICompletionAdapter — a second CompletionAdapter implementation, alongside
GeminiCompletionAdapter, using the `openai` Python SDK directly. `openai` is already a
core (non-extra) dependency of pipecat-ai — confirmed via `pip show pipecat-ai`'s own
requirement list (`openai<3,>=1.74.0`, unconditional) — no new requirements/base.txt entry
needed.
"""

import json
from typing import Any

from openai import AsyncOpenAI


class OpenAICompletionAdapter:
    def __init__(self, *, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        # response_format={"type": "json_object"} (OpenAI's JSON mode) requires the word
        # "json" to appear somewhere in the messages, or the API rejects the request — the
        # one caller today (calls/activities.py's _SUMMARY_SYSTEM_PROMPT) already satisfies
        # this ("Respond with JSON only..."); any new caller of this adapter must too.
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if content is None:
            # e.g. the response was truncated/filtered — a real, if rare, failure mode;
            # raising here (rather than json.loads(None) blowing up with an unclear
            # TypeError) is what generate_call_summary's caller expects to catch. Mirrors
            # gemini_completion.py::GeminiCompletionAdapter's identical guard.
            raise ValueError("OpenAI returned no content in its response")
        return json.loads(content)
