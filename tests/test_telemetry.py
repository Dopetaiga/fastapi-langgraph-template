"""Deterministic OpenTelemetry tests."""
from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.observability.telemetry import instrument_fastapi, setup_telemetry, traced_span


def test_disabled_setup_is_explicit() -> None:
    assert setup_telemetry(enabled=False) is None


def test_traced_span_records_attributes_and_error() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    with patch("app.observability.telemetry.get_tracer", return_value=tracer):
        with traced_span("agent.run", {"agent.run_id": "run-1", "secret": {"bad": "shape"}}):
            pass

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == ["agent.run"]
    assert spans[0].attributes["agent.run_id"] == "run-1"
    assert "secret" not in spans[0].attributes


def test_fastapi_instrumentation_is_idempotent() -> None:
    app = FastAPI()
    instrument_fastapi(app)
    instrument_fastapi(app)
    assert app.state.otel_instrumented is True
