"""A single cached Temporal client for FastAPI request handlers — the HTTP-facing
counterpart to src/database.py's get_session_factory(). Only calls/router.py's `POST
/calls` (an ad-hoc single-attempt entry point) needs this in Phase 1; every other
Temporal interaction happens from within already-running workflow/activity code, which
never needs a client of its own (activities that start a workflow do so as a child of the
calling workflow — see calls/workflows.py's COMPLAINT_REQUEST branch — precisely to avoid
needing a second client connection).
"""

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from src.config import settings

_client: Client | None = None


async def get_temporal_client() -> Client:
    global _client
    if _client is None:
        _client = await Client.connect(
            settings.TEMPORAL_HOST,
            namespace=settings.TEMPORAL_NAMESPACE,
            data_converter=pydantic_data_converter,
        )
    return _client
