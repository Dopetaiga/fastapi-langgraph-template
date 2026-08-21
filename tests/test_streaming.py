"""Tests for SSE streaming endpoint (Phase 10)."""
from __future__ import annotations

import json
import re

import pytest

from app.api.streaming import _sse_event, _redact, register_emitter
from app.core.state import EventType
from app.services.events import EventEmitter
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    return TestClient(create_app())


class TestStreamingEndpoint:
    def test_stream_empty_run(self, client: TestClient):
        resp = client.get("/runs/nonexistent/stream")
        assert resp.status_code == 200

    def test_stream_returns_sse_format(self, client: TestClient):
        emitter = EventEmitter()
        emitter.emit(EventType.run_started, "stream-test-1")
        register_emitter("stream-test-1", emitter)

        resp = client.get("/runs/stream-test-1/stream")
        assert resp.status_code == 200
        content = resp.text
        assert "data:" in content
        assert "run.started" in content

    def test_stream_redacts_sensitive_payload(self, client: TestClient):
        payload = {"api_key": "secret123", "result": "ok"}
        event_str = _sse_event("tool.completed", payload, 0)
        data = json.loads(event_str.replace("data: ", "").strip())
        assert data["payload"]["api_key"] == "***"
        assert data["payload"]["result"] == "ok"

    def test_stream_monotonic_seq(self, client: TestClient):
        emitter = EventEmitter()
        emitter.emit(EventType.run_started, "stream-seq-1")
        emitter.emit(EventType.node_started, "stream-seq-1")
        emitter.emit(EventType.node_completed, "stream-seq-1")
        register_emitter("stream-seq-1", emitter)

        resp = client.get("/runs/stream-seq-1/stream")
        content = resp.text
        events = [json.loads(line.replace("data: ", "").strip())
                  for line in content.strip().split("\n") if line.startswith("data:")]
        seqs = [e["seq"] for e in events]
        assert seqs == sorted(seqs)

    def test_redact_function(self):
        assert _redact({"password": "secret", "name": "safe"}) == {"password": "***", "name": "safe"}
        assert _redact({"token": "x", "data": "y"}) == {"token": "***", "data": "y"}
        assert _redact({"safe_key": "value"}) == {"safe_key": "value"}

    def test_sse_event_format(self):
        event_str = _sse_event("run.completed", {"status": "ok"}, 5)
        assert event_str.startswith("data: ")
        assert event_str.endswith("\n\n")
        data = json.loads(event_str[6:].strip())
        assert data["type"] == "run.completed"
        assert data["seq"] == 5
        assert data["payload"]["status"] == "ok"
