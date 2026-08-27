"""The structural half of spec §2.2.2 rule 2 ("caller speech must never be concatenated
into system/developer prompts as trusted instructions").

`build_system_prompt` accepts exactly one parameter, typed `PromptContext` — a model of
pre-validated, structured fields the calls/ workflow selected (spec §36 rule 4: every
customer-specific sentence must trace to a Pydantic-validated tool response). There is no
`str` parameter anywhere in the signature, so a caller cannot pass raw transcript text into
it even by mistake. tests/unit/test_prompt_structure.py asserts this mechanically.
"""

from pydantic import BaseModel


class PromptContext(BaseModel):
    claim_stage: str
    verification_level: str  # "L0" | "L1" | "L2"
    language: str  # "en" | "ar"
    next_expected_event: str | None = None
    customer_first_name: str | None = None


def build_system_prompt(context: PromptContext) -> str:
    raise NotImplementedError("Phase 2 — voice/pipeline.py wires this to the real prompt")
