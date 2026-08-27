import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.exceptions import (
    IdempotencyConflictError,
    IdempotencyKeyReuseError,
    IdempotentOperationFailedError,
)
from src.idempotency import IdempotencyRecord, _fingerprint, idempotent


async def test_first_call_runs_operation_once(db_session):
    calls = {"n": 0}

    async def op():
        calls["n"] += 1
        return {"result": "ok"}

    result = await idempotent(
        db_session,
        key="k-first",
        correlation_id="c1",
        operation_name="test",
        payload={"a": 1},
        operation=op,
    )
    assert result == {"result": "ok"}
    assert calls["n"] == 1


async def test_replay_returns_cached_result_without_rerunning(db_engine):
    calls = {"n": 0}

    async def op():
        calls["n"] += 1
        return {"result": "ok"}

    async with AsyncSession(db_engine, expire_on_commit=False) as s1:
        await idempotent(
            s1,
            key="k-replay",
            correlation_id="c1",
            operation_name="test",
            payload={"a": 1},
            operation=op,
        )

    async with AsyncSession(db_engine, expire_on_commit=False) as s2:
        result = await idempotent(
            s2,
            key="k-replay",
            correlation_id="c1",
            operation_name="test",
            payload={"a": 1},
            operation=op,
        )
        assert result == {"result": "ok"}
    assert calls["n"] == 1


async def test_mismatched_payload_raises_key_reuse_error(db_engine):
    async def op():
        return {}

    async with AsyncSession(db_engine, expire_on_commit=False) as s1:
        await idempotent(
            s1,
            key="k-mismatch",
            correlation_id="c1",
            operation_name="test",
            payload={"a": 1},
            operation=op,
        )

    async with AsyncSession(db_engine, expire_on_commit=False) as s2:
        with pytest.raises(IdempotencyKeyReuseError):
            await idempotent(
                s2,
                key="k-mismatch",
                correlation_id="c1",
                operation_name="test",
                payload={"a": 2},
                operation=op,
            )


async def test_concurrent_race_resolves_to_exactly_one_execution(db_engine):
    calls = {"n": 0}

    async def slow_op():
        calls["n"] += 1
        await asyncio.sleep(0.15)
        return {"raced": True}

    async def racer():
        async with AsyncSession(db_engine, expire_on_commit=False) as s:
            return await idempotent(
                s,
                key="k-race",
                correlation_id="c-race",
                operation_name="race",
                payload={},
                operation=slow_op,
            )

    results = await asyncio.gather(racer(), racer())
    assert results == [{"raced": True}, {"raced": True}]
    assert calls["n"] == 1


async def test_failing_operation_records_failed_and_reraises(db_session):
    async def failing_op():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await idempotent(
            db_session,
            key="k-fail",
            correlation_id="c1",
            operation_name="test",
            payload={},
            operation=failing_op,
        )


async def test_replay_of_failed_record_raises(db_engine):
    async def failing_op():
        raise ValueError("boom")

    async def op():
        return {}

    async with AsyncSession(db_engine, expire_on_commit=False) as s1:
        with pytest.raises(ValueError):
            await idempotent(
                s1,
                key="k-fail-replay",
                correlation_id="c1",
                operation_name="test",
                payload={},
                operation=failing_op,
            )

    async with AsyncSession(db_engine, expire_on_commit=False) as s2:
        with pytest.raises(IdempotentOperationFailedError):
            await idempotent(
                s2,
                key="k-fail-replay",
                correlation_id="c1",
                operation_name="test",
                payload={},
                operation=op,
            )


async def test_stuck_pending_record_exhausts_poll_budget(db_session, monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "IDEMPOTENCY_POLL_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "IDEMPOTENCY_POLL_INTERVAL_SECONDS", 0.01)

    db_session.add(
        IdempotencyRecord(
            idempotency_key="k-stuck",
            correlation_id="c1",
            operation_name="x",
            request_fingerprint=_fingerprint({}),
            status="PENDING",
        )
    )
    await db_session.commit()

    async def op():
        return {}

    with pytest.raises(IdempotencyConflictError):
        await idempotent(
            db_session,
            key="k-stuck",
            correlation_id="c1",
            operation_name="x",
            payload={},
            operation=op,
        )
