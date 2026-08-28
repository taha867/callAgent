"""CallEligibility (Batch 7) plus RetrySchedulerWorkflow's input/output shapes (Batch 13)."""

from pydantic import BaseModel


class CallEligibility(BaseModel):
    call_eligible: bool
    customer_id: str
    claim_id: str
    cli: str | None = None
    cli_trunk_authorized: bool = False
    contact_window_allowed: bool = False
    ineligible_reason: str | None = None


class RetrySchedulerInput(BaseModel):
    call_job_id: str
    customer_id: str
    claim_id: str
    # One simulated answer result per attempt (task 4/§0.5's answer-detection stub, applied
    # across the whole retry sequence) — index 0 is attempt 1, etc. Missing entries default
    # to "NO_ANSWER", matching the no-answer/retry scenario this workflow exists to drive.
    simulated_answer_results: list[str] = []


class RetrySchedulerOutput(BaseModel):
    disposition_code: str
    attempts_made: int
