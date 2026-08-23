"""Runtime event emitter: in-memory queue of RuntimeEvent instances."""
from __future__ import annotations

import asyncio
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


class DurableEventEmitter(EventEmitter):
    """Persist each emitted event promptly while preserving local test visibility."""

    def __init__(self, repository) -> None:
        super().__init__()
        self._repository = repository
        self._lock = asyncio.Lock()
        self._tasks: list[asyncio.Task] = []

    def emit(
        self,
        type_: EventType,
        run_id: str,
        node: str | None = None,
        payload: dict | None = None,
    ) -> RuntimeEvent:
        event = super().emit(type_, run_id, node, payload)
        self._tasks.append(asyncio.create_task(self._persist(run_id, event)))
        return event

    async def _persist(self, run_id: str, event: RuntimeEvent) -> None:
        async with self._lock:
            await self._repository.append_many(run_id, [event])

    async def drain(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks)
            self._tasks.clear()
