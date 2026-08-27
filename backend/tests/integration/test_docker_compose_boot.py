"""Thin, opt-in sanity check (COMPOSE_SMOKE=1) that a Temporal client can connect and
/health responds. The real compose smoke test lives in CI (.github/workflows/backend-ci.yml,
job compose-smoke) where a failure is easier to debug than inside pytest.
"""

import os

import httpx
import pytest
from temporalio.client import Client

from src.config import settings

pytestmark = pytest.mark.skipif(
    os.environ.get("COMPOSE_SMOKE") != "1",
    reason="set COMPOSE_SMOKE=1 to run against a live docker-compose stack",
)


async def test_temporal_client_connects():
    client = await Client.connect(settings.TEMPORAL_HOST, namespace=settings.TEMPORAL_NAMESPACE)
    assert client is not None


async def test_backend_health_endpoint_responds():
    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8001")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{backend_url}/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
