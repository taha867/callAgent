from http import HTTPStatus

from src.exceptions import CallAgentError, register_status


class ClaimNotFoundError(CallAgentError):
    def __init__(self, claim_id: str) -> None:
        self.claim_id = claim_id
        super().__init__(f"claim not found: {claim_id}")


register_status(ClaimNotFoundError, HTTPStatus.NOT_FOUND)
