"""ComplaintsConfig — insurer SLA policy, stubbed as env-overridable settings for Phase 1
(see .claude/specs/phase-1-backend-spec.md decision 0.9). A real per-insurer-administered
policy table is a later-phase upgrade that swaps this module's internals without touching
its callers — complaints/service.py::create_complaint is the only consumer.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ComplaintsConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ACKNOWLEDGMENT_SLA_HOURS: int = 24
    RESOLUTION_SLA_DAYS: int = 9
    # spec §18.1's "configured warning threshold before ... due_at" — how long before a
    # deadline ComplaintSlaMonitorWorkflow (Batch 15) raises COMPLAINT_SLA_AT_RISK.
    SLA_WARNING_HOURS: int = 4


complaints_settings = ComplaintsConfig()  # type: ignore[call-arg]
