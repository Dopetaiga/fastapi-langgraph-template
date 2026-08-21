"""SSE streaming endpoint for run events."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.state import EventType
from app.services.events import EventEmitter

router = APIRouter(prefix="/runs", tags=["streaming"])

# In-memory event store: run_id -> EventEmitter
_run_emitters: dict[str, EventEmitter] = {}


def get_emitter(run_id: str) -> EventEmitter:
    if run_id not in _run_emitters:
        _run_emitters[run_id] = EventEmitter()
    return _run_emitters[run_id]


def register_emitter(run_id: str, emitter: EventEmitter) -> None:
    _run_emitters[run_id] = emitter


@router.get("/{run_id}/stream")
async def stream_run_events(run_id: str, request: Request, after_seq: int = -1):
    """SSE endpoint streaming run events."""
    emitter = get_emitter(run_id)

    async def event_generator():
        terminal_types = {EventType.run_completed, EventType.run_failed}
        sent: set[int] = set()
        max_iterations = 100
        for _ in range(max_iterations):
            pending = [e for e in emitter.all_events() if e.seq > after_seq and e.seq not in sent]
            if not pending:
                return
            for event in pending:
                sent.add(event.seq)
                yield _sse_event(event.type.value, event.payload, event.seq)
                if event.type in terminal_types:
                    return
            await asyncio.sleep(0.02)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse_event(event_type: str, payload: dict, seq: int) -> str:
    data = {"type": event_type, "seq": seq, "payload": _redact(payload)}
    return f"data: {json.dumps(data)}\n\n"


def _redact(payload: dict) -> dict:
    """Redact sensitive fields from events."""
    sensitive = {"api_key", "password", "secret", "token"}
    return {k: ("***" if k.lower() in sensitive else v) for k, v in payload.items()}
