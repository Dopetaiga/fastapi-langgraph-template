"""Memory API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.capabilities.memory import MemoryService, MemoryFact

router = APIRouter(prefix="/memory", tags=["memory"])

_memory = MemoryService()


def get_memory() -> MemoryService:
    return _memory


class MemoryPutRequest(BaseModel):
    user_id: str
    key: str
    value: dict
    namespace: str = "user"
    team_id: str | None = None


class MemoryGetResponse(BaseModel):
    user_id: str
    key: str
    value: dict
    namespace: str
    team_id: str | None = None


class TeamMemoryPutRequest(BaseModel):
    team_id: str
    key: str
    value: dict


@router.post("/user", response_model=MemoryGetResponse)
async def put_user_memory(req: MemoryPutRequest, memory: MemoryService = Depends(get_memory)):
    fact = MemoryFact(user_id=req.user_id, key=req.key, value=req.value, namespace=req.namespace, team_id=req.team_id)
    memory.put(fact)
    return MemoryGetResponse(user_id=req.user_id, key=req.key, value=req.value, namespace=req.namespace, team_id=req.team_id)


@router.get("/user/{user_id}", response_model=list[MemoryGetResponse])
async def get_user_memory(user_id: str, memory: MemoryService = Depends(get_memory)):
    facts = memory.get_all(user_id)
    return [
        MemoryGetResponse(user_id=f.user_id, key=f.key, value=f.value, namespace=f.namespace, team_id=f.team_id)
        for f in facts
    ]


@router.get("/user/{user_id}/{key}", response_model=MemoryGetResponse)
async def get_user_memory_key(user_id: str, key: str, memory: MemoryService = Depends(get_memory)):
    fact = memory.get(user_id, key)
    if fact is None:
        raise HTTPException(status_code=404, detail="memory key not found")
    return MemoryGetResponse(user_id=fact.user_id, key=fact.key, value=fact.value, namespace=fact.namespace, team_id=fact.team_id)


@router.post("/team", response_model=MemoryGetResponse)
async def put_team_memory(req: TeamMemoryPutRequest, memory: MemoryService = Depends(get_memory)):
    fact = MemoryFact(user_id=req.team_id, key=req.key, value=req.value, namespace="team", team_id=req.team_id)
    memory.put(fact)
    return MemoryGetResponse(user_id=req.team_id, key=req.key, value=req.value, namespace="team", team_id=req.team_id)


@router.get("/team/{team_id}", response_model=list[MemoryGetResponse])
async def get_team_memory(team_id: str, memory: MemoryService = Depends(get_memory)):
    facts = memory.get_all(team_id, namespace="team", team_id=team_id)
    return [
        MemoryGetResponse(user_id=f.user_id, key=f.key, value=f.value, namespace=f.namespace, team_id=f.team_id)
        for f in facts
    ]
