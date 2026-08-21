"""Worker queue: PostgreSQL-backed job queue with SKIP LOCKED."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select, update

from app.core.state import RunStatus
from app.db.engine import get_session
from app.models.db import JobModel, RunModel
from app.services.errors import GraphValidationError


class WorkerQueue:
    """PostgreSQL-backed job queue using SKIP LOCKED."""

    def __init__(self, handler: Callable[[JobModel], None]) -> None:
        self._handler = handler

    async def enqueue(self, run_id: str) -> JobModel:
        """Create a new job for a run."""
        job = JobModel(id=str(uuid.uuid4()), run_id=run_id, status="queued")
        async for session in get_session():
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return job
        raise RuntimeError("session generator exhausted")

    async def claim_next(self) -> JobModel | None:
        """Claim one pending job atomically."""
        async for session in get_session():
            stmt = (
                select(JobModel)
                .where(JobModel.status == "queued")
                .order_by(JobModel.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            result = await session.execute(stmt)
            job = result.scalar_one_or_none()
            if job is None:
                return None
            job.status = "running"
            job.claimed_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(job)
            return job
        raise RuntimeError("session generator exhausted")

    async def complete(self, job_id: str) -> None:
        async for session in get_session():
            stmt = (
                update(JobModel)
                .where(JobModel.id == job_id)
                .values(status="completed", finished_at=datetime.now(timezone.utc))
            )
            await session.execute(stmt)
            await session.commit()
            return
        raise RuntimeError("session generator exhausted")

    async def fail(self, job_id: str, error: str) -> None:
        async for session in get_session():
            stmt = (
                update(JobModel)
                .where(JobModel.id == job_id)
                .values(status="failed", error=error, finished_at=datetime.now(timezone.utc))
            )
            await session.execute(stmt)
            await session.commit()
            return
        raise RuntimeError("session generator exhausted")

    async def run_once(self) -> bool:
        """Claim and process one job. Returns True if a job was processed."""
        job = await self.claim_next()
        if job is None:
            return False
        try:
            await self._set_run_status(job.run_id, RunStatus.running)
            self._handler(job)
            await self.complete(job.id)
            await self._set_run_status(job.run_id, RunStatus.completed)
        except Exception as exc:
            await self.fail(job.id, str(exc))
            await self._set_run_status(job.run_id, RunStatus.failed, error=str(exc))
        return True

    async def _set_run_status(self, run_id: str, status: RunStatus, error: str | None = None) -> None:
        async for session in get_session():
            stmt = (
                update(RunModel)
                .where(RunModel.id == run_id)
                .values(status=status.value, error=error, updated_at=datetime.now(timezone.utc))
            )
            await session.execute(stmt)
            await session.commit()
            return
        raise RuntimeError("session generator exhausted")

    async def run_forever(self, poll_interval: float = 1.0) -> None:
        """Run worker loop until cancelled."""
        import asyncio
        while True:
            processed = await self.run_once()
            if not processed:
                await asyncio.sleep(poll_interval)
