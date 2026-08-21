"""Runtime event emitter: in-memory queue of RuntimeEvent instances."""
from __future__ import annotations

from collections import deque

from app.core.state import EventType, RuntimeEvent


class EventEmitter:
    """Thread-safe in-memory event queue for a single run."""

    def __init__(self) -> None:
        self._events: deque[RuntimeEvent] = deque()
        self._seq: int = 0
        self._subscribers: list[callable] = []

    def emit(self, type_: EventType, run_id: str, node: str | None = None, payload: dict | None = None) -> RuntimeEvent:
        evt = RuntimeEvent(
            seq=self._seq,
            type=type_,
            run_id=run_id,
            node=node,
            payload=payload or {},
        )
        self._seq += 1
        self._events.append(evt)
        for sub in self._subscribers:
            try:
                sub(evt)
            except Exception:
                pass
        return evt

    def subscribe(self, callback: callable) -> None:
        self._subscribers.append(callback)

    def all_events(self) -> list[RuntimeEvent]:
        return list(self._events)

    def latest_seq(self) -> int:
        return max((e.seq for e in self._events), default=-1)

    def clear(self) -> None:
        self._events.clear()
        self._seq = 0
