from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Free-text (length-bounded, pattern-validated) — NOT FK'd to DispositionCode/ActionCode.
# See .claude/specs/phase-0-backend-spec.md decision 2: spec §32's own examples
# ("AUTHENTICATION_FAILED", "CALL_TERMINATED_WITH_OFFICIAL_SUPPORT_OPTION") aren't drawn
# from the §24/§25 code lists — they're a separate, per-decision explanation vocabulary.
_DecisionCodeStr = Annotated[str, Field(min_length=3, max_length=120, pattern=r"^[A-Z][A-Z0-9_]*$")]


class AuditEventCreate(BaseModel):
    call_id: str | None = None
    correlation_id: str | None = None
    actor: Literal["SYSTEM", "AI", "HUMAN"] = "SYSTEM"
    decision: _DecisionCodeStr
    reason_code: _DecisionCodeStr
    policy_rule: _DecisionCodeStr | None = None
    action_taken: _DecisionCodeStr | None = None
    metadata: dict[str, Any] | None = None


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    call_id: str | None
    correlation_id: str | None
    actor: str
    decision: str
    reason_code: str
    policy_rule: str | None
    action_taken: str | None
    metadata_json: dict[str, Any] | None
    created_at: datetime
