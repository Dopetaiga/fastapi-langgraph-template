"""Durable Server-Sent Events endpoint backed by PostgreSQL."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.observability.telemetry import sse_connections, sse_events
from app.services.event_repository import RuntimeEventRepository

router = APIRouter(prefix="/runs", tags=["streaming"])
_event_repository = RuntimeEventRepository()


def get_event_repository() -> RuntimeEventRepository:
    return _event_repository


@router.get("/{run_id}/stream")
async def stream_run_events(
    run_id: str,
    request: Request,
    after_seq: int = -1,
    repository: RuntimeEventRepository = Depends(get_event_repository),
) -> StreamingResponse:
    """Replay durable events, then tail until terminal state or disconnect."""
    if not await repository.run_exists(run_id):
        raise HTTPException(status_code=404, detail="run not found")
    header_id = request.headers.get("last-event-id")
    cursor = int(header_id) if header_id is not None else after_seq

    async def event_generator() -> AsyncIterator[str]:
        nonlocal cursor
        sse_connections.add(1)
        terminal_types = {"run.completed", "run.failed", "run.cancelled"}
        idle_polls = 0
        try:
            while not await request.is_disconnected():
                pending = await repository.list_after(run_id, cursor)
                if pending:
                    idle_polls = 0
                    for event in pending:
                        cursor = event.seq
                        sse_events.add(1, {"event.type": event.type})
                        yield _sse_event(event.type, event.payload, event.seq, event.node)
                        if event.type in terminal_types:
                            return
                    continue
                if await repository.run_is_terminal_or_paused(run_id):
                    return
                idle_polls += 1
                if idle_polls % 15 == 0:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(1.0)
        finally:
            sse_connections.add(-1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _sse_event(event_type: str, payload: dict, seq: int, node: str | None = None) -> str:
    data = {"type": event_type, "seq": seq, "node": node, "payload": payload}
    return (
        f"id: {seq}\n"
        f"event: {event_type}\n"
        f"data: {json.dumps(data, separators=(',', ':'))}\n\n"
    )
