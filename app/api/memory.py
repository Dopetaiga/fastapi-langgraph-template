"""Long-term memory API backed by the project-owned Mem0 adapter."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.capabilities.memory_store import Mem0MemoryStore, MemoryRecord, MemoryStore
from app.core.config import settings

router = APIRouter(prefix="/memory", tags=["memory"])
_memory_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    global _memory_store
    if not settings.mem0_enabled or not settings.mem0_api_key:
        raise HTTPException(status_code=503, detail="Mem0 is not configured")
    if _memory_store is None:
        _memory_store = Mem0MemoryStore.create(
            api_key=settings.mem0_api_key,
            data_dir=settings.mem0_data_dir,
        )
    return _memory_store


class MemoryAddRequest(BaseModel):
    messages: list[dict[str, str]]
    metadata: dict = Field(default_factory=dict)


class MemorySearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)


class MemoryResponse(BaseModel):
    memories: list[MemoryRecord]


@router.post("/{user_id}", response_model=MemoryResponse)
async def add_memory(
    user_id: str,
    request: MemoryAddRequest,
    store: MemoryStore = Depends(get_memory_store),
) -> MemoryResponse:
    if not request.messages:
        raise HTTPException(status_code=422, detail="messages must not be empty")
    records = await store.add(
        user_id=user_id,
        messages=request.messages,
        metadata=request.metadata,
    )
    return MemoryResponse(memories=records)


@router.post("/{user_id}/search", response_model=MemoryResponse)
async def search_memory(
    user_id: str,
    request: MemorySearchRequest,
    store: MemoryStore = Depends(get_memory_store),
) -> MemoryResponse:
    return MemoryResponse(memories=await store.search(
        user_id=user_id,
        query=request.query,
        top_k=request.top_k,
    ))


@router.get("/{user_id}", response_model=MemoryResponse)
async def list_memory(
    user_id: str,
    page: int = 1,
    page_size: int = 50,
    store: MemoryStore = Depends(get_memory_store),
) -> MemoryResponse:
    if page < 1 or not 1 <= page_size <= 100:
        raise HTTPException(status_code=422, detail="invalid pagination")
    return MemoryResponse(memories=await store.list(
        user_id=user_id,
        page=page,
        page_size=page_size,
    ))
