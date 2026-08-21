"""Run management API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.state import RunStatus
from app.models.db import RunModel
from app.runtime.run_manager import RunManager
from app.services.events import EventEmitter

router = APIRouter(prefix="/runs", tags=["runs"])

_run_manager: RunManager | None = None
_event_store: dict[str, EventEmitter] = {}


def get_run_manager() -> RunManager:
    global _run_manager
    if _run_manager is None:
        _run_manager = RunManager(graphs_dir="graphs")
    return _run_manager


class CreateRunRequest(BaseModel):
    session_id: str
    graph_name: str = "default"
    input_text: str


class RunResponse(BaseModel):
    run_id: str
    status: RunStatus
    graph_name: str
    input_text: str
    output_text: str | None = None
    error: str | None = None
    termination_reason: str | None = None


@router.post("", response_model=RunResponse)
async def create_run(req: CreateRunRequest, manager: RunManager = Depends(get_run_manager)):
    run = await manager.create_run(req.session_id, req.graph_name, req.input_text)
    return RunResponse(
        run_id=run.id,
        status=RunStatus(run.status),
        graph_name=run.graph_name,
        input_text=run.input_text,
    )


@router.post("/{run_id}/execute", response_model=RunResponse)
async def execute_run(run_id: str, manager: RunManager = Depends(get_run_manager)):
    from app.db.engine import get_session
    from sqlalchemy import select
    async for session in get_session():
        result = await session.execute(select(RunModel).where(RunModel.id == run_id))
        run = result.scalar_one_or_none()
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        break

    input_text = run.input_text
    result = await manager.execute_run_sync(run_id, input_text)
    return RunResponse(
        run_id=result["run_id"],
        status=result["status"],
        graph_name=run.graph_name,
        input_text=input_text,
        output_text=result["output"],
        termination_reason=result["termination_reason"],
    )


@router.get("/{run_id}/events")
async def get_run_events(run_id: str, after_seq: int = -1):
    emitter = _event_store.get(run_id)
    if emitter is None:
        return {"events": [], "latest_seq": -1}
    events = emitter.all_events()
    filtered = [e for e in events if e.seq > after_seq]
    return {"events": [e.model_dump() for e in filtered], "latest_seq": emitter.latest_seq()}
