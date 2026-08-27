import httpx
import pytest
from fastapi import Depends, FastAPI

from src.exceptions import OutboundDisabledError
from src.kill_switch import assert_outbound_enabled, require_outbound_enabled


def test_all_flags_on_passes(set_flags):
    set_flags(
        GLOBAL_OUTBOUND_ENABLED=True,
        CAMPAIGN_ENABLED=True,
        CLI_ENABLED=True,
        AI_AUTOMATION_ENABLED=True,
    )
    assert_outbound_enabled("campaign", "cli")  # does not raise


def test_global_off_overrides_every_per_gate_flag(set_flags):
    set_flags(
        GLOBAL_OUTBOUND_ENABLED=False,
        CAMPAIGN_ENABLED=True,
        CLI_ENABLED=True,
        AI_AUTOMATION_ENABLED=True,
    )
    with pytest.raises(OutboundDisabledError) as exc_info:
        assert_outbound_enabled("campaign")
    assert exc_info.value.flag_name == "GLOBAL_OUTBOUND_ENABLED"


def test_per_gate_isolation(set_flags):
    set_flags(GLOBAL_OUTBOUND_ENABLED=True, CAMPAIGN_ENABLED=False, CLI_ENABLED=True)
    with pytest.raises(OutboundDisabledError) as exc_info:
        assert_outbound_enabled("campaign")
    assert exc_info.value.flag_name == "CAMPAIGN_ENABLED"

    assert_outbound_enabled("cli")  # unaffected gate does not raise


async def test_fastapi_dependency_returns_503(set_flags):
    """The test that would have caught an `async def` dependency-factory bug: if
    require_outbound_enabled returned a coroutine instead of a sync callable, Depends()
    would misbehave rather than cleanly returning 503."""
    app = FastAPI()

    @app.get("/x", dependencies=[Depends(require_outbound_enabled("campaign"))])
    async def endpoint():
        return {"ok": True}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        set_flags(GLOBAL_OUTBOUND_ENABLED=True, CAMPAIGN_ENABLED=True)
        response = await client.get("/x")
        assert response.status_code == 200

        set_flags(CAMPAIGN_ENABLED=False)
        response = await client.get("/x")
        assert response.status_code == 503
