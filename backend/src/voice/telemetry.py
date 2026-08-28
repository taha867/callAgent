"""OpenTelemetry tracing setup — spec §2.2.1's per-hop P50/P95/P99 requirement is satisfied
by Pipecat's OWN native tracing, not hand-instrumented spans. Confirmed via direct
`pipecat-ai==1.8.1` package introspection: `PipelineWorker(enable_tracing=True)` already
wires `pipecat.utils.tracing.turn_trace_observer.TurnTraceObserver`, which creates a
per-conversation span with a per-turn child span for every conversation turn, and STT/LLM/
TTS service spans nest under each turn span automatically — exactly spec §2.2.1's chain
(STT -> orchestration/LLM -> TTS-first-byte -> total turn), without this codebase
duplicating that instrumentation by hand.

This module's only job is the standard OpenTelemetry SDK setup Pipecat's tracing plugs
into. `voice_server.py` calls `configure_tracing()` once at process startup, before any
pipeline runs; `voice/pipeline.py` passes `enable_tracing=True` plus a call-scoped
`additional_span_attributes` dict when constructing each call's `PipelineWorker`.
"""

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_configured = False


def configure_tracing(*, service_name: str = "callagent-voice") -> None:
    """Idempotent — safe to call more than once (e.g. from tests) without stacking
    duplicate exporters onto the global tracer provider."""
    global _configured
    if _configured:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    _configured = True
