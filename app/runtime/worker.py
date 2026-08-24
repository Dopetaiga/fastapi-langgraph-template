"""Worker queue: PostgreSQL-backed job queue with SKIP LOCKED."""
from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from opentelemetry import context as otel_context
from opentelemetry.propagate import extract, inject
from sqlalchemy import and_, or_, select, update

from app.core.state import TERMINAL_RUN_STATUSES, EventType, RunStatus, RuntimeEvent
from app.db.engine import get_session
from app.models.db import JobModel, RunModel
from app.observability.telemetry import traced_span, worker_jobs, worker_queue_delay
from app.services.errors import JobLeaseLostError, JobNotRetryable
from app.services.event_repository import RuntimeEventRepository

logger = logging.getLogger(__name__)


class WorkerQueue:
    """PostgreSQL-backed job queue using SKIP LOCKED."""

    def __init__(
        self,
        handler: Callable[[JobModel], object | Awaitable[object]],
        *,
        worker_id: str | None = None,
        lease_seconds: int = 60,
        retry_delay_seconds: int = 5,
        event_repository: RuntimeEventRepository | None = None,
    ) -> None:
        self._handler = handler
        self.worker_id = worker_id or f"worker-{uuid.uuid4()}"
        self.lease_seconds = lease_seconds
        self.retry_delay_seconds = retry_delay_seconds
        self._event_repository = event_repository or RuntimeEventRepository()

    async def enqueue(self, run_id: str) -> JobModel:
        """Create a new job for a run."""
        trace_context: dict[str, str] = {}
        inject(trace_context)
        job = JobModel(
            id=str(uuid.uuid4()),
            run_id=run_id,
            status="queued",
            attempt_count=0,
            max_attempts=3,
            trace_context=trace_context,
        )
        async for session in get_session():
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return job
        raise RuntimeError("session generator exhausted")

    async def claim_next(self) -> JobModel | None:
        """Claim one pending job atomically."""
        now = datetime.now(UTC)
        async for session in get_session():
            stmt = (
                select(JobModel)
                .join(RunModel, RunModel.id == JobModel.run_id)
                .where(
                    RunModel.status.notin_([
                        RunStatus.completed.value,
                        RunStatus.failed.value,
                        RunStatus.cancelled.value,
                    ]),
                    or_(
                        JobModel.status == "queued",
                        and_(
                            JobModel.status == "retry_wait",
                            or_(JobModel.next_attempt_at.is_(None), JobModel.next_attempt_at <= now),
                        ),
                        and_(
                            JobModel.status == "running",
                            JobModel.lease_expires_at < now,
                        ),
                    ),
                )
                .order_by(JobModel.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            result = await session.execute(stmt)
            job = result.scalar_one_or_none()
            if job is None:
                return None
            job.status = "running"
            job.lease_owner = self.worker_id
            job.claimed_at = now
            job.heartbeat_at = now
            job.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
            job.attempt_count = (job.attempt_count or 0) + 1
            job.next_attempt_at = None
            await session.commit()
            await session.refresh(job)
            if job.created_at is not None:
                created = job.created_at if job.created_at.tzinfo else job.created_at.replace(tzinfo=UTC)
                worker_queue_delay.record(max(0.0, (now - created).total_seconds()))
            return job
        raise RuntimeError("session generator exhausted")

    async def complete(self, job_id: str) -> None:
        async for session in get_session():
            stmt = (
                update(JobModel)
                .where(JobModel.id == job_id, JobModel.lease_owner == self.worker_id)
                .values(
                    status="completed",
                    finished_at=datetime.now(UTC),
                    lease_owner=None,
                    lease_expires_at=None,
                )
            )
            await session.execute(stmt)
            await session.commit()
            return
        raise RuntimeError("session generator exhausted")

    async def fail(self, job_id: str, error: str) -> None:
        async for session in get_session():
            result = await session.execute(
                select(JobModel)
                .where(JobModel.id == job_id, JobModel.lease_owner == self.worker_id)
                .with_for_update()
            )
            job = result.scalar_one_or_none()
            if job is None:
                return
            now = datetime.now(UTC)
            job.error = error
            job.lease_owner = None
            job.lease_expires_at = None
            if (job.attempt_count or 0) < (job.max_attempts or 3):
                job.status = "retry_wait"
                job.next_attempt_at = now + timedelta(seconds=self.retry_delay_seconds)
            else:
                job.status = "failed"
                job.finished_at = now
            await session.commit()
            return
        raise RuntimeError("session generator exhausted")

    async def heartbeat(self, job_id: str) -> bool:
        """Extend a lease owned by this worker."""
        now = datetime.now(UTC)
        async for session in get_session():
            result = await session.execute(
                update(JobModel)
                .where(
                    JobModel.id == job_id,
                    JobModel.status == "running",
                    JobModel.lease_owner == self.worker_id,
                )
                .values(
                    heartbeat_at=now,
                    lease_expires_at=now + timedelta(seconds=self.lease_seconds),
                )
            )
            await session.commit()
            return bool(result.rowcount)
        raise RuntimeError("session generator exhausted")

    async def run_once(self) -> bool:
        """Claim and process one job. Returns True if a job was processed."""
        job = await self.claim_next()
        if job is None:
            return False
        carrier = job.trace_context if isinstance(job.trace_context, dict) else {}
        token = otel_context.attach(extract(carrier))
        try:
            with traced_span("worker.job", {
                "agent.run_id": job.run_id,
                "agent.job_id": job.id,
                "agent.job.attempt": job.attempt_count,
            }):
                await self._set_run_status(job.run_id, RunStatus.running)
                stop_heartbeat = asyncio.Event()
                lease_lost = asyncio.Event()
                handler_task = asyncio.create_task(self._invoke_handler(job))
                heartbeat_task = asyncio.create_task(
                    self._heartbeat_loop(job.id, stop_heartbeat, handler_task, lease_lost)
                )
                try:
                    handler_result = await handler_task
                except asyncio.CancelledError:
                    if lease_lost.is_set():
                        raise JobLeaseLostError(f"job {job.id} lost its lease") from None
                    # Shutdown cancellation: stop the handler deterministically.
                    handler_task.cancel()
                    await asyncio.gather(handler_task, return_exceptions=True)
                    raise
                finally:
                    stop_heartbeat.set()
                    await asyncio.gather(heartbeat_task, return_exceptions=True)
                await self.complete(job.id)
                # Handler may return the Run status it observed. Only promote a
                # non-terminal Run to completed; paused/cancelled/failed keep
                # the state written by the execution path or the cancel API.
                if not isinstance(handler_result, RunStatus) or handler_result == RunStatus.completed:
                    await self._set_run_status(job.run_id, RunStatus.completed)
            worker_jobs.add(1, {"status": "paused" if handler_result == RunStatus.paused else "completed"})
        except JobLeaseLostError:
            # Another worker owns the job now; it drives the outcome.
            worker_jobs.add(1, {"status": "lease_lost"})
            logger.warning("job %s lease lost; aborting handler", job.id)
        except JobNotRetryable as exc:
            # Deterministic failure: retrying would reproduce it identically.
            worker_jobs.add(1, {"status": "failed"})
            await self._fail_without_retry(job.id, str(exc))
            await self._set_run_status(job.run_id, RunStatus.failed, error=str(exc))
            await self._emit_run_failed(job.run_id, str(exc), job.attempt_count)
        except Exception as exc:
            worker_jobs.add(1, {"status": "failed"})
            await self.fail(job.id, str(exc))
            attempts_exhausted = (job.attempt_count or 0) >= (job.max_attempts or 3)
            await self._set_run_status(
                job.run_id,
                RunStatus.failed if attempts_exhausted else RunStatus.queued,
                error=str(exc),
            )
            if attempts_exhausted:
                await self._emit_run_failed(job.run_id, str(exc), job.attempt_count)
        finally:
            otel_context.detach(token)
        return True

    async def _fail_without_retry(self, job_id: str, error: str) -> None:
        async for session in get_session():
            stmt = (
                update(JobModel)
                .where(JobModel.id == job_id, JobModel.lease_owner == self.worker_id)
                .values(
                    status="failed",
                    error=error,
                    finished_at=datetime.now(UTC),
                    lease_owner=None,
                    lease_expires_at=None,
                )
            )
            await session.execute(stmt)
            await session.commit()
            return
        raise RuntimeError("session generator exhausted")

    async def _emit_run_failed(self, run_id: str, error: str, attempts: int | None) -> None:
        await self._event_repository.append_many(run_id, [RuntimeEvent(
            seq=0,
            type=EventType.run_failed,
            run_id=run_id,
            payload={"error": error, "attempts": attempts},
        )])

    async def _invoke_handler(self, job: JobModel):
        handler_result = self._handler(job)
        if inspect.isawaitable(handler_result):
            handler_result = await handler_result
        return handler_result

    async def _heartbeat_loop(
        self,
        job_id: str,
        stop: asyncio.Event,
        handler_task: asyncio.Task,
        lease_lost: asyncio.Event,
    ) -> None:
        interval = max(1.0, self.lease_seconds / 3)
        while True:
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
                return
            except TimeoutError:
                if not await self.heartbeat(job_id):
                    # Lease was taken over: stop duplicating external work.
                    lease_lost.set()
                    handler_task.cancel()
                    return

    async def _set_run_status(self, run_id: str, status: RunStatus, error: str | None = None) -> None:
        """Write run status without mutating an already terminal Run."""
        async for session in get_session():
            stmt = (
                update(RunModel)
                .where(
                    RunModel.id == run_id,
                    (RunModel.status.notin_(TERMINAL_RUN_STATUSES))
                    | (RunModel.status == status.value),
                )
                .values(status=status.value, error=error, updated_at=datetime.now(UTC))
            )
            await session.execute(stmt)
            await session.commit()
            return
        raise RuntimeError("session generator exhausted")

    async def run_forever(self, poll_interval: float = 1.0) -> None:
        """Run worker loop until cancelled; transient poll failures back off."""
        consecutive_failures = 0
        while True:
            try:
                processed = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                consecutive_failures += 1
                delay = min(self.retry_delay_seconds * (2 ** min(consecutive_failures - 1, 5)), 60.0)
                logger.exception("worker poll failed; retrying in %.1fs", delay)
                await asyncio.sleep(delay)
                continue
            consecutive_failures = 0
            if not processed:
                await asyncio.sleep(poll_interval)

