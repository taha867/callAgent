"""DefectLogEntry, JourneyRunResult — Phase 4 governance, .claude/specs/phase-4-backend-spec.md
§0.4/§3. Dev-process QA metadata, NOT a runtime call audit trail — deliberately plain
mutable rows (no @enforce_insert_only), unlike audit_event/runtime_failure_event/
complaint_sla_event: a defect legitimately moves OPEN -> FIX_APPLIED -> COMPILED and its
occurrence_count is incremented in place, the same "soft-delete/status-transition pattern"
CLAUDE.md §2.5 already uses for Complaint.

`id` columns default to a generated UUID, same convention as complaints/models.py::Complaint.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base


class DefectLogEntry(Base):
    __tablename__ = "qa_defect_log_entry"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str]
    defect_shape_key: Mapped[str] = mapped_column(index=True)
    demo_journey_id: Mapped[str | None] = mapped_column(default=None)
    adversarial_scenario_id: Mapped[str | None] = mapped_column(default=None)
    language: Mapped[str] = mapped_column(default="EN")  # "EN" | "AR" | "CODE_SWITCH"
    severity: Mapped[str] = mapped_column(default="MEDIUM")  # "LOW" | "MEDIUM" | "HIGH"
    status: Mapped[str] = mapped_column(default="OPEN")  # DefectStatus
    occurrence_count: Mapped[int] = mapped_column(default=1)
    compiled_artifact_type: Mapped[str | None] = mapped_column(default=None)  # CompiledArtifactType
    compiled_artifact_ref: Mapped[str | None] = mapped_column(default=None)
    first_seen_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]
    notes: Mapped[str | None] = mapped_column(default=None)


class JourneyRunResult(Base):
    __tablename__ = "qa_journey_run_result"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    demo_journey_id: Mapped[str]  # DemoJourneyId
    adversarial_scenario_id: Mapped[str | None] = mapped_column(default=None)  # null = cooperative baseline
    passed: Mapped[bool]
    run_at: Mapped[datetime]
    defect_log_entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("qa_defect_log_entry.id"), default=None
    )
    test_node_id: Mapped[str]
