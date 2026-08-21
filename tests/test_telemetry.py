"""Tests for observability/telemetry (Phase 11)."""
from __future__ import annotations

import pytest


class TestTelemetrySetup:
    def test_setup_no_crash_without_packages(self):
        """setup_telemetry should not crash even if opentelemetry is not installed."""
        from app.observability.telemetry import setup_telemetry
        setup_telemetry()  # should be a no-op

    def test_get_tracer_returns_noop(self):
        """get_tracer returns a no-op tracer when packages are missing."""
        from app.observability.telemetry import get_tracer
        tracer = get_tracer()
        span = tracer.start_as_current_span("test")
        with span:
            pass  # no-op

    def test_instrument_fastapi_no_crash(self):
        """instrument_fastapi should not crash without packages."""
        from app.observability.telemetry import instrument_fastapi
        from fastapi import FastAPI
        app = FastAPI()
        instrument_fastapi(app)  # no-op
