"""Emit one trace, metric set, and correlated log to the local OTLP Collector."""
import logging

from app.observability.telemetry import (
    record_llm_usage,
    setup_telemetry,
    shutdown_telemetry,
    traced_span,
    worker_jobs,
)

setup_telemetry(
    service_name="agent-runtime-observability-smoke",
    enabled=True,
    metrics_export_interval_ms=1000,
)
worker_jobs.add(1, {"status": "completed"})
record_llm_usage("smoke-model", {"prompt_tokens": 7, "completion_tokens": 3}, 0.001)
with traced_span("observability.smoke"):
    logging.getLogger("smoke").info("observability pipeline smoke")
shutdown_telemetry()
