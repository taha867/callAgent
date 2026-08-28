"""Shared exception base classes and the error-response schema.

Framework-agnostic on purpose (no FastAPI imports here) — worker.py and any Temporal
activity reuse these same exception types without pulling in FastAPI, per CLAUDE.md §2.2
("raise a domain exception in the service ... reusable from worker.py/voice_server.py,
which never touch FastAPI at all").
"""

from http import HTTPStatus

from pydantic import BaseModel

# Domain-local exception modules (src/<domain>/exceptions.py) define their own exception
# classes and call register_status() (below) once per HTTP-facing exception, at import
# time, to add themselves to EXCEPTION_STATUS_MAP — the one shared registry main.py's
# global CallAgentError handler consults. A domain exception nobody registers falls back
# to 500 (status_for()'s default) — deliberate, so a forgotten mapping fails loudly in a
# smoke test rather than silently returning the wrong status code.


class CallAgentError(Exception):
    """Root of every domain exception in this codebase."""


class OutboundDisabledError(CallAgentError):
    """Raised by src.kill_switch when a kill-switch flag blocks an outbound-triggering
    code path. spec §39."""

    def __init__(self, flag_name: str) -> None:
        self.flag_name = flag_name
        super().__init__(f"outbound disabled: {flag_name} is false")


class AuditEventImmutableError(CallAgentError):
    """Raised whenever code attempts to UPDATE, DELETE, or bulk-mutate an audit_event row.
    CLAUDE.md §2.5: audit/event tables are insert-only, enforced, not just documented."""


class InsertOnlyTableViolationError(CallAgentError):
    """Raised by src.insert_only's shared ORM guard for any Phase-1+ insert-only table
    (runtime_failure_event, complaint_sla_event) that isn't audit_event itself — which
    keeps its own, earlier, specifically-named AuditEventImmutableError above rather than
    being refactored onto this shared mechanism (see src/insert_only.py's docstring)."""

    def __init__(self, table_name: str) -> None:
        self.table_name = table_name
        super().__init__(f"{table_name} rows cannot be updated or deleted (append-only)")


class UnknownToolError(CallAgentError):
    """Raised by voice.tools.dispatch_tool_call for any name outside TOOL_REGISTRY.
    spec §2.2.2 rule 3 / §21."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"unknown or disallowed tool: {name}")


class IdempotencyError(CallAgentError):
    """Root of the idempotency exception family — src.idempotency.idempotent()."""


class IdempotencyKeyReuseError(IdempotencyError):
    """The same idempotency key was reused with a different request payload."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"idempotency key reused with a different payload: {key}")


class IdempotencyConflictError(IdempotencyError):
    """A PENDING record never resolved within the configured poll budget."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"idempotent operation still pending, retry shortly: {key}")


class IdempotentOperationFailedError(IdempotencyError):
    """Replay of a key whose original attempt FAILED. The caller must mint a new key —
    see .claude/specs/phase-0-backend-spec.md decision 1: retrying blindly under the same
    key risks re-attempting a write whose outcome is uncertain (spec §36 rule 27)."""

    def __init__(self, key: str, original_error: str) -> None:
        self.key = key
        self.original_error = original_error
        super().__init__(f"idempotency key {key} previously failed: {original_error}")


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None


EXCEPTION_STATUS_MAP: dict[type[CallAgentError], int] = {
    OutboundDisabledError: HTTPStatus.SERVICE_UNAVAILABLE,
    AuditEventImmutableError: HTTPStatus.INTERNAL_SERVER_ERROR,
    InsertOnlyTableViolationError: HTTPStatus.INTERNAL_SERVER_ERROR,
    UnknownToolError: HTTPStatus.BAD_REQUEST,
    IdempotencyKeyReuseError: HTTPStatus.UNPROCESSABLE_ENTITY,
    IdempotencyConflictError: HTTPStatus.CONFLICT,
    IdempotentOperationFailedError: HTTPStatus.CONFLICT,
}


def status_for(exc: CallAgentError) -> int:
    for exc_type, status_code in EXCEPTION_STATUS_MAP.items():
        if isinstance(exc, exc_type):
            return status_code
    return HTTPStatus.INTERNAL_SERVER_ERROR


def register_status(exc_type: type[CallAgentError], status_code: int) -> None:
    """Lets a domain's own exceptions.py register its HTTP status mapping without
    src/exceptions.py importing that domain (which would invert the dependency direction
    CLAUDE.md §2.2 describes: this module must stay framework/domain-agnostic, reusable
    from worker.py/voice_server.py with zero domain coupling). Each domain's
    exceptions.py calls this once, at import time, for every exception its own routers can
    raise — see src/claims/exceptions.py for the pattern."""
    EXCEPTION_STATUS_MAP[exc_type] = status_code
