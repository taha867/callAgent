"""The Pipecat real-time server process — Phase 2's third deployable process alongside
main.py (HTTP API) and worker.py (Temporal worker), per CLAUDE.md §2.1. Never a Temporal
worker itself and never hosts CallSessionWorkflow — it is a Temporal *client*, signaling
into a workflow `worker.py`'s own process already runs, exactly the way
tests/integration/test_phase1_e2e.py's fake/text harness already did
(.claude/specs/phase-2-backend-spec.md §0.1).

Built on Pipecat's own local-dev runner (`pipecat.runner.run`), which already implements
the WebRTC signaling server (`/start`/offer-answer exchange) and a browser test UI for local
bot development — no hand-rolled aiohttp app or custom demo client page needed (a real
simplification over an earlier sketch of this file, found once the installed package was
inspected directly; see .claude/specs/phase-2-backend-spec.md's Batch 8 correction).

Run locally: `python voice_server.py` (serves on port 8765 by default, restrict to WebRTC
with `-t webrtc`). In Docker: the `voice` service in docker-compose.yml.
"""

import logging

import aiohttp
from pipecat.runner.types import RunnerArguments, SmallWebRTCRunnerArguments

from src.temporal_client import get_temporal_client
from src.voice.adapters.telephony import build_transport
from src.voice.config import voice_settings
from src.voice.pipeline import run_call_pipeline
from src.voice.telemetry import configure_tracing

logger = logging.getLogger("voice_server")


async def _start_call(*, customer_id: str, claim_id: str) -> str:
    """Starts the CallSessionWorkflow via the existing, kill-switch-gated `POST /calls`
    endpoint (calls/router.py::start_call) rather than calling `client.start_workflow()`
    directly — going straight to Temporal from here would silently bypass
    `Depends(require_outbound_enabled("ai_automation"))`, spec §39's outbound kill switch.
    Routing through the same REST endpoint a campaign-triggered call would use keeps that
    gate meaningful for every call this system originates, demo or otherwise."""
    async with (
        aiohttp.ClientSession() as session,
        session.post(
            f"{voice_settings.BACKEND_BASE_URL}/calls",
            json={"customer_id": customer_id, "claim_id": claim_id},
        ) as response,
    ):
        response.raise_for_status()
        data = await response.json()
        return str(data["call_id"])


async def bot(runner_args: RunnerArguments) -> None:
    """Pipecat's dev runner discovers and calls this once per accepted connection."""
    if not isinstance(runner_args, SmallWebRTCRunnerArguments):
        logger.error(
            "voice_server.py only supports the browser WebRTC transport this phase "
            "(spec's $0-recurring-spend demo tier) — got %s",
            type(runner_args).__name__,
        )
        return

    # The browser-demo transport has no real inbound call to trigger a workflow start for
    # (unlike a campaign-triggered outbound call) — a fixed demo customer/claim, optionally
    # overridden per-connection via the client's /start request body, stands in for that.
    body = runner_args.body or {}
    customer_id = body.get("customer_id") or voice_settings.VOICE_DEMO_CUSTOMER_ID
    claim_id = body.get("claim_id") or voice_settings.VOICE_DEMO_CLAIM_ID
    if not customer_id or not claim_id:
        logger.error(
            "No customer_id/claim_id available — set VOICE_DEMO_CUSTOMER_ID/"
            "VOICE_DEMO_CLAIM_ID in .env, or pass them in the /start request body."
        )
        return

    call_id = await _start_call(customer_id=customer_id, claim_id=claim_id)
    transport = build_transport(runner_args.webrtc_connection)
    client = await get_temporal_client()
    await run_call_pipeline(
        call_id=call_id,
        customer_id=customer_id,
        claim_id=claim_id,
        transport=transport,
        client=client,
    )


if __name__ == "__main__":
    configure_tracing()

    from pipecat.runner.run import main

    main()
