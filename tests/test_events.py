"""Tests for EventEmitter."""
from __future__ import annotations

from app.core.state import EventType, RuntimeEvent
from app.services.events import EventEmitter


class TestEventEmitter:
    def test_emit_creates_event(self):
        emitter = EventEmitter()
        e = emitter.emit(EventType.run_started, "r1")
        assert e.type == EventType.run_started
        assert e.seq == 0

    def test_emit_increments_seq(self):
        emitter = EventEmitter()
        e1 = emitter.emit(EventType.run_started, "r1")
        e2 = emitter.emit(EventType.node_started, "r1")
        assert e1.seq == 0
        assert e2.seq == 1

    def test_emit_with_node_and_payload(self):
        emitter = EventEmitter()
        e = emitter.emit(EventType.tool_started, "r1", node="calc", payload={"args": [1, 2]})
        assert e.node == "calc"
        assert e.payload == {"args": [1, 2]}

    def test_all_events_tracked(self):
        emitter = EventEmitter()
        for et in EventType:
            emitter.emit(et, "r1")
        events = emitter.all_events()
        assert len(events) == len(EventType)

    def test_latest_seq(self):
        emitter = EventEmitter()
        emitter.emit(EventType.run_started, "r1")
        emitter.emit(EventType.node_started, "r1")
        assert emitter.latest_seq() == 1

    def test_clear(self):
        emitter = EventEmitter()
        emitter.emit(EventType.run_started, "r1")
        emitter.clear()
        assert len(emitter.all_events()) == 0
        assert emitter.latest_seq() == -1

    def test_subscribe(self):
        emitter = EventEmitter()
        received = []

        def callback(e):
            received.append(e)

        emitter.subscribe(callback)
        emitter.emit(EventType.run_started, "r1")
        assert len(received) == 1
