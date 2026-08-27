"""IdempotencyRecord model + the `idempotent()` wrapper every customer-impacting write
reachable from the live-call path will use starting Phase 1 (spec §10.6.4, §36 rule 27:
"network uncertainty must never create duplicate customer-impacting actions").

Transaction contract: `idempotent()` commits `session`. Callers must not wrap it in an
outer `async with session.begin():` — the claim phase and the execute/finalize phase are
each their own committed transaction by design (see the module docstring on `idempotent`
below for why).
"""

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.config import settings
from src.exceptions import (
    IdempotencyConflictError,
    IdempotencyKeyReuseError,
    IdempotentOperationFailedError,
)
from src.models import Base

IdempotencyStatus = Literal["PENDING", "COMPLETED", "FAILED"]


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_record"

    idempotency_key: Mapped[str] = mapped_column(primary_key=True)
    correlation_id: Mapped[str] = mapped_column(index=True)
    operation_name: Mapped[str]
    request_fingerprint: Mapped[str]
    status: Mapped[str] = mapped_column(default="PENDING")
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(default=None)


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


async def idempotent(
    session: AsyncSession,
    *,
    key: str,
    correlation_id: str,
    operation_name: str,
    payload: dict[str, Any],
    operation: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """Run `operation()` exactly once per `key`, replay-safe across retries.

    Phase A — claim: insert a PENDING row for `key` in its own SAVEPOINT and commit
    immediately. Committing the claim before running `operation()` (rather than holding a
    single transaction open for the operation's full duration) is deliberate: it makes
    PENDING observable to a concurrent retry immediately, bounding the primary-key lock
    window to microseconds instead of the operation's entire runtime.

    Phase B — execute: run `operation()`, record COMPLETED/FAILED, commit, return/raise.

    Phase C — replay/poll (on a claim conflict): roll back, re-SELECT fresh (the identity
    map can otherwise hand back a stale cached row under READ COMMITTED), check the
    fingerprint first (a reused key with a different payload is always an error, even if
    the original attempt also failed), then branch on stored status. PENDING polls up to
    `IDEMPOTENCY_POLL_ATTEMPTS` times before raising a 409-mapped conflict.
    """
    fingerprint = _fingerprint(payload)

    try:
        async with session.begin_nested():
            session.add(
                IdempotencyRecord(
                    idempotency_key=key,
                    correlation_id=correlation_id,
                    operation_name=operation_name,
                    request_fingerprint=fingerprint,
                    status="PENDING",
                )
            )
            await session.flush()
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return await _replay_or_poll(session, key=key, fingerprint=fingerprint)

    try:
        result = await operation()
    except Exception as exc:
        await _finalize(
            session,
            key,
            status="FAILED",
            response_body={"error_type": type(exc).__name__, "error": str(exc)},
        )
        raise
    else:
        await _finalize(session, key, status="COMPLETED", response_body=result)
        return result


async def _finalize(
    session: AsyncSession, key: str, *, status: IdempotencyStatus, response_body: dict[str, Any]
) -> None:
    record = await session.get(IdempotencyRecord, key)
    assert record is not None
    record.status = status
    record.response_body = response_body
    record.completed_at = func.now()  # type: ignore[assignment]
    await session.commit()


async def _replay_or_poll(session: AsyncSession, *, key: str, fingerprint: str) -> dict[str, Any]:
    attempts = settings.IDEMPOTENCY_POLL_ATTEMPTS
    for attempt in range(attempts):
        record = (
            await session.execute(
                select(IdempotencyRecord).where(IdempotencyRecord.idempotency_key == key)
            )
        ).scalar_one()

        if record.request_fingerprint != fingerprint:
            raise IdempotencyKeyReuseError(key)

        if record.status == "COMPLETED":
            return record.response_body or {}
        if record.status == "FAILED":
            error_message = (record.response_body or {}).get("error", "unknown error")
            raise IdempotentOperationFailedError(key, error_message)

        # still PENDING
        if attempt == attempts - 1:
            break
        await asyncio.sleep(settings.IDEMPOTENCY_POLL_INTERVAL_SECONDS)
        await session.rollback()
        session.expire_all()

    raise IdempotencyConflictError(key)
