from src.exceptions import CallAgentError


class CampaignError(CallAgentError):
    """Root of the campaigns exception family."""


class ClaimNotFoundForEligibilityCheckError(CampaignError):
    pass
