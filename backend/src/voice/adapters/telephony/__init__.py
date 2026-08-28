"""Telephony transport selection — see stt/__init__.py's module docstring for the pattern
this mirrors. "browser" (WebRTC, via Pipecat's own SmallWebRTCTransport) is the only
demo-tier option this phase — no real PSTN calling, per IMPLEMENTATION_PLAN.md's $0-recurring
-spend demo strategy. A real telephony vendor transport (Twilio, a UAE carrier trunk) is
Phase 6's paid-vendor swap: a new branch here, never a change to voice/pipeline.py.

Unlike the STT/TTS/LLM factories, transport construction needs a per-call connection object
(the WebRTC peer connection negotiated by voice_server.py's offer handler) — there is
nothing to construct ahead of time.
"""

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection


def build_transport(webrtc_connection: SmallWebRTCConnection) -> BaseTransport:
    from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

    return SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            # Pipecat's native VAD/barge-in support — satisfies the phase file's
            # "interruption handling via Pipecat's native support" task via configuration.
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )
