"""DefectLogEntryCreate/Read/Update, DefectOccurrenceCreate, JourneyRunCreate/Read,
GovernanceSummary — CLAUDE.md §2.4's three-schema convention.

`compilation_required` on DefectLogEntryRead is computed server-side only (qa/service.py),
never client-settable — same discipline CLAUDE.md §2.4 requires of ComplaintRead's SLA
fields: getting this wrong would defeat the entire mechanical point of the two-strike CI
gate (.claude/specs/phase-4-backend-spec.md §0.5/§6.2).
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class DefectLogEntryCreate(BaseModel):
    title: Annotated[str, Field(max_length=200)]
    defect_shape_key: Annotated[str, Field(max_length=100)]
    demo_journey_id: str | None = None
    adversarial_scenario_id: str | None = None
    language: Annotated[str, Field(pattern="^(EN|AR|CODE_SWITCH)$")] = "EN"
    severity: Annotated[str, Field(pattern="^(LOW|MEDIUM|HIGH)$")] = "MEDIUM"
    notes: Annotated[str | None, Field(max_length=2000)] = None


class DefectLogEntryRead(DefectLogEntryCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    occurrence_count: int
    compiled_artifact_type: str | None
    compiled_artifact_ref: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    compilation_required: bool


class DefectLogEntryUpdate(BaseModel):
    status: Annotated[str | None, Field(pattern="^(OPEN|FIX_APPLIED|COMPILED|WONT_FIX)$")] = None
    compiled_artifact_type: Annotated[
        str | None, Field(pattern="^(REGRESSION_TEST|GUARD_PHRASE_RULE|TOOL_ALLOWLIST_RULE|NON_NEGOTIABLE_RULE)$")
    ] = None
    compiled_artifact_ref: Annotated[str | None, Field(max_length=300)] = None
    notes: Annotated[str | None, Field(max_length=2000)] = None


class DefectOccurrenceCreate(BaseModel):
    demo_journey_id: str | None = None
    adversarial_scenario_id: str | None = None
    notes: Annotated[str | None, Field(max_length=2000)] = None


class JourneyRunCreate(BaseModel):
    demo_journey_id: str
    adversarial_scenario_id: str | None = None
    passed: bool
    test_node_id: Annotated[str, Field(max_length=300)]
    defect_log_entry_id: str | None = None


class JourneyRunRead(JourneyRunCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_at: datetime


class GovernanceSummary(BaseModel):
    total_defects: int
    open_defects: int
    compilation_required_count: int
    journeys_passing: int
    journeys_total: int = 9
