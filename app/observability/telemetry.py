"""OpenTelemetry instrumentation module.

Note: opentelemetry packages are optional. Install with:
  pip install opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-fastapi opentelemetry-exporter-otlp
"""
from __future__ import annotations

_tracer = None


def setup_telemetry(service_name: str = "agent-runtime", otlp_endpoint: str = "http://localhost:4317") -> None:
    """Initialize OpenTelemetry tracing. No-op if packages not installed."""
    global _tracer
    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        processor = SimpleSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(__name__)
    except ImportError:
        pass


def instrument_fastapi(app) -> None:
    """Auto-instrument FastAPI app. No-op if packages not installed."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except ImportError:
        pass


def get_tracer():
    """Return tracer if available, else a no-op."""
    global _tracer
    if _tracer is not None:
        return _tracer
    try:
        from opentelemetry import trace
        _tracer = trace.get_tracer(__name__)
        return _tracer
    except ImportError:
        return _NoOpTracer()


class _NoOpTracer:
    def start_as_current_span(self, name, **kwargs):
        return _NoOpContextManager()


class _NoOpContextManager:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass
