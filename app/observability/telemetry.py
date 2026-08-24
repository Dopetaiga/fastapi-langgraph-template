"""OpenTelemetry bootstrap for traces, metrics, and correlated logs."""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.trace import Status, StatusCode

_lock = Lock()
_provider: TracerProvider | None = None
_meter_provider: MeterProvider | None = None
_logger_provider: LoggerProvider | None = None
_httpx_instrumented = False


class JsonFormatter(logging.Formatter):
    """Compact stdout JSON with trace correlation; never serializes arbitrary objects."""

    def format(self, record: logging.LogRecord) -> str:
        span_context = trace.get_current_span().get_span_context()
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if span_context.is_valid:
            payload["trace_id"] = format(span_context.trace_id, "032x")
            payload["span_id"] = format(span_context.span_id, "016x")
        for key in ("run_id", "job_id", "node_id", "event_type"):
            value = getattr(record, key, None)
            if isinstance(value, (str, int, float, bool)):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def create_tracer_provider(service_name: str, exporter: SpanExporter) -> TracerProvider:
    """Create an isolated provider; useful for deterministic tests."""
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


def setup_telemetry(
    service_name: str = "agent-runtime",
    otlp_endpoint: str = "http://localhost:4317",
    *,
    insecure: bool = True,
    enabled: bool = True,
    metrics_export_interval_ms: int = 15000,
    log_level: str = "INFO",
    log_json: bool = True,
) -> TracerProvider | None:
    """Configure all three OTLP signals and Python log correlation exactly once."""
    global _provider, _meter_provider, _logger_provider, _httpx_instrumented
    if not enabled:
        return None
    with _lock:
        if _provider is not None:
            return _provider
        resource = Resource.create({"service.name": service_name})
        _provider = create_tracer_provider(
            service_name, OTLPSpanExporter(endpoint=otlp_endpoint, insecure=insecure)
        )
        trace.set_tracer_provider(_provider)

        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=otlp_endpoint, insecure=insecure),
            export_interval_millis=metrics_export_interval_ms,
        )
        _meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(_meter_provider)

        _logger_provider = LoggerProvider(resource=resource)
        _logger_provider.add_log_record_processor(BatchLogRecordProcessor(
            OTLPLogExporter(endpoint=otlp_endpoint, insecure=insecure)
        ))
        set_logger_provider(_logger_provider)
        root = logging.getLogger()
        root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        if log_json and not any(getattr(h, "_agent_json", False) for h in root.handlers):
            console = logging.StreamHandler()
            console.setFormatter(JsonFormatter())
            console._agent_json = True  # type: ignore[attr-defined]
            root.addHandler(console)
        if not any(isinstance(h, LoggingHandler) for h in root.handlers):
            root.addHandler(LoggingHandler(logger_provider=_logger_provider))
        if not _httpx_instrumented:
            HTTPXClientInstrumentor().instrument()
            _httpx_instrumented = True
        return _provider


def instrument_fastapi(app) -> None:
    """Instrument one FastAPI application without tracing health probes."""
    if getattr(app.state, "otel_instrumented", False):
        return
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health")
    app.state.otel_instrumented = True


def get_tracer(name: str = "agent-runtime"):
    return trace.get_tracer(name)


def get_meter(name: str = "agent-runtime"):
    return metrics.get_meter(name)


_meter = get_meter()
operation_count = _meter.create_counter(
    "agent_runtime.operation.count", description="Completed runtime operations"
)
operation_duration = _meter.create_histogram(
    "agent_runtime.operation.duration", unit="s", description="Runtime operation latency"
)
llm_tokens = _meter.create_counter(
    "gen_ai.client.token.usage", unit="{token}", description="LLM input and output tokens"
)
llm_cost = _meter.create_counter(
    "gen_ai.client.cost", unit="USD", description="Provider-reported LLM cost"
)
worker_jobs = _meter.create_counter("agent_runtime.worker.jobs", description="Worker job outcomes")
worker_queue_delay = _meter.create_histogram(
    "agent_runtime.worker.queue.delay", unit="s", description="Time from enqueue to claim"
)
sse_connections = _meter.create_up_down_counter(
    "agent_runtime.sse.connections", description="Active SSE connections"
)
sse_events = _meter.create_counter("agent_runtime.sse.events", description="SSE events delivered")
llm_calls = _meter.create_counter(
    "agent_runtime.llm.calls",
    description="LLM call outcomes (call-level, distinct from worker job outcomes)",
)
catalog_refreshes = _meter.create_counter(
    "agent_runtime.model.catalog.refresh",
    description="Model catalog refresh outcomes",
)


def record_llm_outcome(model: str, *, outcome: str, fallback: bool = False) -> None:
    llm_calls.add(1, {
        "gen_ai.request.model": model,
        "outcome": outcome,
        "fallback": fallback,
    })


def record_catalog_refresh(*, status: str, model_count: int) -> None:
    catalog_refreshes.add(1, {"status": status})
    if status == "fresh":
        _catalog_models_gauge_note(model_count)


def _catalog_models_gauge_note(count: int) -> None:
    # Kept as a log-only observation; a gauge would need an observable
    # callback and adds little for the demo dashboards.
    logger = logging.getLogger(__name__)
    logger.info(
        "model catalog refreshed",
        extra={"event_type": "model.catalog.refreshed", "models": count},
    )


def record_operation(operation: str, duration_seconds: float, status: str, **dimensions: str) -> None:
    attrs = {"operation": operation, "status": status, **dimensions}
    operation_count.add(1, attrs)
    operation_duration.record(duration_seconds, attrs)


def record_llm_usage(model: str, usage: dict[str, Any], cost_usd: float | None = None) -> None:
    aliases = (("input", "prompt_tokens"), ("output", "completion_tokens"))
    for token_type, key in aliases:
        value = usage.get(key)
        if isinstance(value, (int, float)):
            llm_tokens.add(int(value), {"gen_ai.request.model": model, "gen_ai.token.type": token_type})
    if isinstance(cost_usd, (int, float)) and cost_usd >= 0:
        llm_cost.add(cost_usd, {"gen_ai.request.model": model})


@contextmanager
def traced_span(
    name: str,
    attributes: dict[str, Any] | None = None,
    *,
    tracer_name: str = "agent-runtime",
) -> Iterator[Any]:
    """Create a span, record errors, and avoid attaching sensitive values."""
    started = time.perf_counter()
    status = "ok"
    with get_tracer(tracer_name).start_as_current_span(name) as span:
        for key, value in (attributes or {}).items():
            if value is not None and isinstance(value, (str, bool, int, float)):
                span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            status = "error"
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            raise
        finally:
            record_operation(name, time.perf_counter() - started, status)


def shutdown_telemetry() -> None:
    if _logger_provider is not None:
        _logger_provider.shutdown()
    if _meter_provider is not None:
        _meter_provider.shutdown()
    if _provider is not None:
        _provider.shutdown()
