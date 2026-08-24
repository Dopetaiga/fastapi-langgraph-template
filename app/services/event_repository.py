"""PostgreSQL source of truth for user-visible runtime events."""
from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.state import RuntimeEvent
from app.db.engine import get_session
from app.models.db import RunEventModel, RunModel


class RuntimeEventRepository:
    async def append_many(self, run_id: str, events: Iterable[RuntimeEvent]) -> None:
        pending = list(events)
        if not pending:
            return
        async for session in get_session():
            # Serialize sequence allocation per Run across workers.
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:run_id))"),
                {"run_id": run_id},
            )
            result = await session.execute(
                select(func.coalesce(func.max(RunEventModel.seq), -1)).where(
                    RunEventModel.run_id == run_id
                )
            )
            next_seq = int(result.scalar_one()) + 1
            for offset, event in enumerate(pending):
                await session.execute(
                    pg_insert(RunEventModel)
                    .values(
                        id=str(uuid.uuid4()),
                        seq=next_seq + offset,
                        run_id=run_id,
                        type=event.type.value,
                        node=event.node,
                        payload=_redact(event.payload),
                    )
                    .on_conflict_do_nothing()
                )
            await session.commit()
            return
        raise RuntimeError("session generator exhausted")

    async def list_after(self, run_id: str, after_seq: int = -1) -> list[RunEventModel]:
        async for session in get_session():
            result = await session.execute(
                select(RunEventModel)
                .where(RunEventModel.run_id == run_id, RunEventModel.seq > after_seq)
                .order_by(RunEventModel.seq)
            )
            return list(result.scalars())
        raise RuntimeError("session generator exhausted")

    async def has_event(self, run_id: str, type_value: str) -> bool:
        """Return True if the run already persisted an event of the given type."""
        async for session in get_session():
            result = await session.execute(
                select(RunEventModel.id)
                .where(RunEventModel.run_id == run_id, RunEventModel.type == type_value)
                .limit(1)
            )
            return result.scalar_one_or_none() is not None
        raise RuntimeError("session generator exhausted")

    async def run_exists(self, run_id: str) -> bool:
        async for session in get_session():
            return await session.get(RunModel, run_id) is not None
        raise RuntimeError("session generator exhausted")

    async def run_is_terminal_or_paused(self, run_id: str) -> bool:
        async for session in get_session():
            status = await session.scalar(select(RunModel.status).where(RunModel.id == run_id))
            return status in {"paused", "completed", "failed", "cancelled"}
        raise RuntimeError("session generator exhausted")


def _redact(value):
    sensitive = {"api_key", "authorization", "password", "secret", "token"}
    if isinstance(value, dict):
        return {
            key: "***" if key.lower() in sensitive else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
