from http import HTTPStatus

from src.exceptions import CallAgentError, register_status


class BackendUnavailableError(CallAgentError):
    """Raised by with_runtime_recovery() when a wrapped activity's dependency call times
    out or the connection fails — spec §10.6.1/§14 Type E. Caught by
    CallSessionWorkflow's status-delivery stage, never improvised past."""

    def __init__(self, component: str) -> None:
        self.component = component
        super().__init__(f"backend dependency unavailable: {component}")


class CallAttemptNotFoundError(CallAgentError):
    def __init__(self, call_id: str) -> None:
        self.call_id = call_id
        super().__init__(f"call attempt not found: {call_id}")


register_status(CallAttemptNotFoundError, HTTPStatus.NOT_FOUND)
