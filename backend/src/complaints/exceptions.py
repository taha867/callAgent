from http import HTTPStatus

from src.exceptions import CallAgentError, register_status


class ComplaintNotFoundError(CallAgentError):
    def __init__(self, complaint_id: str) -> None:
        self.complaint_id = complaint_id
        super().__init__(f"complaint not found: {complaint_id}")


register_status(ComplaintNotFoundError, HTTPStatus.NOT_FOUND)
