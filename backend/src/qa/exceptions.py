from http import HTTPStatus

from src.exceptions import CallAgentError, register_status


class DefectLogEntryNotFoundError(CallAgentError):
    def __init__(self, entry_id: str) -> None:
        self.entry_id = entry_id
        super().__init__(f"defect log entry not found: {entry_id}")


class DefectShapeKeyNotFoundError(CallAgentError):
    def __init__(self, shape_key: str) -> None:
        self.shape_key = shape_key
        super().__init__(f"no existing defect with shape key: {shape_key}")


register_status(DefectLogEntryNotFoundError, HTTPStatus.NOT_FOUND)
register_status(DefectShapeKeyNotFoundError, HTTPStatus.NOT_FOUND)
