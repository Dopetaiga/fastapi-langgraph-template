"""Project-owned long-term-memory boundary and the single Mem0 adapter."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.observability.telemetry import traced_span


class MemoryRecord(BaseModel):
    id: str | None = None
    text: str
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryStore(Protocol):
    async def add(
        self,
        *,
        user_id: str,
        messages: list[dict[str, str]],
        metadata: dict[str, Any] | None = None,
    ) -> list[MemoryRecord]: ...

    async def search(self, *, user_id: str, query: str, top_k: int = 5) -> list[MemoryRecord]: ...

    async def list(self, *, user_id: str, page: int = 1, page_size: int = 50) -> list[MemoryRecord]: ...


class Mem0MemoryStore:
    """Mem0 Platform adapter; no Mem0 response type escapes this module."""

    def __init__(self, client: Any) -> None:
        self._client = client

    @classmethod
    def create(cls, *, api_key: str, data_dir: str = ".runtime/mem0") -> Mem0MemoryStore:
        # Mem0 currently initializes a local telemetry identity at import time.
        # Keep that side effect inside a configured, project-owned runtime path.
        path = Path(data_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("MEM0_DIR", str(path))
        from mem0 import AsyncMemoryClient

        return cls(AsyncMemoryClient(api_key=api_key))

    async def add(
        self,
        *,
        user_id: str,
        messages: list[dict[str, str]],
        metadata: dict[str, Any] | None = None,
    ) -> list[MemoryRecord]:
        with traced_span("memory.add", {"memory.user_id": user_id}):
            response = await self._client.add(
                messages=messages,
                user_id=user_id,
                metadata=metadata or {},
            )
        return _records(response)

    async def search(self, *, user_id: str, query: str, top_k: int = 5) -> list[MemoryRecord]:
        with traced_span("memory.search", {
            "memory.user_id": user_id,
            "memory.top_k": top_k,
        }):
            response = await self._client.search(
                query=query,
                filters={"user_id": user_id},
                top_k=top_k,
            )
        return _records(response)

    async def list(
        self,
        *,
        user_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> list[MemoryRecord]:
        with traced_span("memory.list", {"memory.user_id": user_id}):
            response = await self._client.get_all(
                filters={"user_id": user_id},
                page=page,
                page_size=page_size,
            )
        return _records(response)


def _records(response: Any) -> list[MemoryRecord]:
    if response is None:
        return []
    payload = response.model_dump() if hasattr(response, "model_dump") else response
    if isinstance(payload, dict):
        rows = payload.get("results", [])
    elif isinstance(payload, list):
        rows = payload
    else:
        return []
    records: list[MemoryRecord] = []
    for row in rows:
        if hasattr(row, "model_dump"):
            row = row.model_dump()
        if not isinstance(row, dict):
            continue
        text = row.get("memory") or row.get("text") or row.get("content")
        if text is None:
            continue
        records.append(MemoryRecord(
            id=str(row["id"]) if row.get("id") is not None else None,
            text=str(text),
            score=float(row["score"]) if row.get("score") is not None else None,
            metadata=dict(row.get("metadata") or {}),
        ))
    return records
