"""Run management API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.state import EventType, RunStatus, RuntimeEvent
from app.models.db import RunModel
from app.runtime.run_manager import RunManager
from app.services.event_repository import RuntimeEventRepository

router = APIRouter(prefix="/runs", tags=["runs"])

_run_manager: RunManager | None = None
_event_repository = RuntimeEventRepository()


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
    created_at: str | None = None
    updated_at: str | None = None


def _response(run: RunModel) -> RunResponse:
    return RunResponse(
        run_id=run.id,
        status=RunStatus(run.status),
        graph_name=run.graph_name,
        input_text=run.input_text,
        output_text=run.output_text,
        error=run.error,
        termination_reason=run.termination_reason,
        created_at=run.created_at.isoformat() if run.created_at else None,
        updated_at=run.updated_at.isoformat() if run.updated_at else None,
    )


@router.post("", response_model=RunResponse)
async def create_run(req: CreateRunRequest, manager: RunManager = Depends(get_run_manager)):
    try:
        run = await manager.create_run(req.session_id, req.graph_name, req.input_text)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _response(run)


@router.get("", response_model=list[RunResponse])
async def list_runs(limit: int = 50):
    from sqlalchemy import select

    from app.db.engine import get_session

    bounded_limit = max(1, min(limit, 200))
    async for session in get_session():
        result = await session.execute(
            select(RunModel).order_by(RunModel.created_at.desc()).limit(bounded_limit)
        )
        return [_response(run) for run in result.scalars()]
    raise RuntimeError("session generator exhausted")


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: str):
    from sqlalchemy import select

    from app.db.engine import get_session

    async for session in get_session():
        result = await session.execute(select(RunModel).where(RunModel.id == run_id))
        run = result.scalar_one_or_none()
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return _response(run)
    raise RuntimeError("session generator exhausted")


@router.post("/{run_id}/execute", response_model=RunResponse)
async def execute_run(run_id: str):
    raise HTTPException(
        status_code=409,
        detail="runs are executed asynchronously by the PostgreSQL worker",
    )


@router.post("/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(run_id: str):
    from sqlalchemy import select

    from app.db.engine import get_session

    async for session in get_session():
        result = await session.execute(
            select(RunModel).where(RunModel.id == run_id).with_for_update()
        )
        run = result.scalar_one_or_none()
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        if run.status in {
            RunStatus.completed.value,
            RunStatus.failed.value,
            RunStatus.cancelled.value,
        }:
            raise HTTPException(status_code=409, detail="terminal run is immutable")
        run.status = RunStatus.cancelled.value
        await session.commit()
        await session.refresh(run)
        await _event_repository.append_many(run_id, [RuntimeEvent(
            seq=0,
            type=EventType.run_cancelled,
            run_id=run_id,
            payload={"reason": "user_cancelled"},
        )])
        return _response(run)
    raise RuntimeError("session generator exhausted")


@router.get("/{run_id}/events")
async def get_run_events(run_id: str, after_seq: int = -1):
    events = await _event_repository.list_after(run_id, after_seq)
    return {
        "events": [
            {
                "seq": event.seq,
                "type": event.type,
                "run_id": event.run_id,
                "node": event.node,
                "payload": event.payload,
                "created_at": event.created_at,
            }
            for event in events
        ],
        "latest_seq": events[-1].seq if events else after_seq,
    }
