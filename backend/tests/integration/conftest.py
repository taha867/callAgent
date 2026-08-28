"""Temporal test fixtures — isolated from tests/unit/conftest.py's DB fixtures so unit
tests never pay for a Temporal connection.
"""

import pytest_asyncio
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment

from src.config import settings


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def temporal_env():
    """Tries settings.TEMPORAL_HOST first (CI service container / a locally running
    docker-compose Temporal) and falls back to WorkflowEnvironment.start_local() (a
    downloaded dev server) if that connection fails — same test suite works whether or not
    a real Temporal is already up, with no code change. Not time-skipping: the Phase 0
    smoke workflow has no timers, so time-skipping buys nothing and its test server has
    known behavioral gaps.
    """
    try:
        client = await Client.connect(
            settings.TEMPORAL_HOST,
            namespace=settings.TEMPORAL_NAMESPACE,
            data_converter=pydantic_data_converter,
        )
        env = WorkflowEnvironment.from_client(client)
    except RuntimeError:
        env = await WorkflowEnvironment.start_local(data_converter=pydantic_data_converter)

    yield env
    await env.shutdown()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def temporal_time_skipping_env():
    """For campaigns.workflows.RetrySchedulerWorkflow / complaints.workflows.
    ComplaintSlaMonitorWorkflow tests only — their workflow.sleep() calls span real hours/
    days (spec §6.1's attempt windows, §18.1's SLA deadlines). `temporal_env` above is
    explicitly NOT time-skipping (fine for Phase 0/1's timer-free workflows); reusing it for
    a multi-hour-sleep workflow would hang or time out the test instead of completing in
    test time.

    Unlike `temporal_env`, this always starts its own local time-skipping test server —
    time-skipping is a property of Temporal's *test* server, not something a real
    already-running Temporal (docker-compose's `temporal` service) can be asked to do.
    """
    env = await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter)
    yield env
    await env.shutdown()
