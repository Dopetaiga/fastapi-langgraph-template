"""Tests for WorkerQueue (Phase 7)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.state import RunStatus
from app.runtime.worker import WorkerQueue


def _make_queue():
    calls = []
    def handler(job):
        calls.append(job)
    return WorkerQueue(handler=handler), calls


class FakeEventRepository:
    def __init__(self):
        self.events = []

    async def append_many(self, _run_id, events):
        self.events.extend(events)


class TestWorkerQueueInterface:
    def test_handler_receives_job(self):
        """run_once passes claimed job to handler."""
        queue, calls = _make_queue()
        fake_job = MagicMock()
        fake_job.id = "job-1"
        fake_job.run_id = "run-1"
        fake_job.attempt_count = 1
        fake_job.max_attempts = 3

        async def run():
            with patch.object(queue, "claim_next", AsyncMock(return_value=fake_job)):
                with patch.object(queue, "complete", AsyncMock()):
                    with patch.object(queue, "fail", AsyncMock()):
                        with patch.object(queue, "_set_run_status", AsyncMock()):
                            result = await queue.run_once()
                            assert result is True
                            assert len(calls) == 1
                            assert calls[0] == fake_job

        asyncio.run(run())

    def test_run_once_no_jobs(self):
        """run_once returns False when no jobs available."""
        queue, calls = _make_queue()

        async def run():
            with patch.object(queue, "claim_next", AsyncMock(return_value=None)):
                result = await queue.run_once()
                assert result is False
                assert calls == []

        asyncio.run(run())

    def test_run_once_handles_error(self):
        """run_once fails job when handler raises."""
        events = FakeEventRepository()
        queue, _ = _make_queue()
        queue._event_repository = events
        fake_job = MagicMock()
        fake_job.id = "job-err"
        fake_job.run_id = "run-err"
        fake_job.attempt_count = 1
        fake_job.max_attempts = 3

        def bad_handler(job):
            raise RuntimeError("boom")

        queue._handler = bad_handler

        async def run():
            with patch.object(queue, "claim_next", AsyncMock(return_value=fake_job)):
                with patch.object(queue, "fail", AsyncMock()) as mock_fail:
                    with patch.object(queue, "_set_run_status", AsyncMock()):
                        result = await queue.run_once()
                        assert result is True
                        mock_fail.assert_called_once()

        asyncio.run(run())
        # a recoverable failure schedules a task-level retry event
        assert [event.type.value for event in events.events] == ["llm.retrying"]
        assert events.events[0].payload["scope"] == "worker_job"

    def test_run_once_awaits_async_handler(self):
        handled = []

        async def handler(job):
            handled.append(job.id)

        queue = WorkerQueue(handler=handler)
        fake_job = MagicMock(id="job-async", run_id="run-async")
        fake_job.id = "job-async"
        fake_job.run_id = "run-async"
        fake_job.attempt_count = 1
        fake_job.max_attempts = 3

        async def run():
            with patch.object(queue, "claim_next", AsyncMock(return_value=fake_job)):
                with patch.object(queue, "complete", AsyncMock()):
                    with patch.object(queue, "_set_run_status", AsyncMock()):
                        assert await queue.run_once() is True

        asyncio.run(run())
        assert handled == ["job-async"]

    def test_run_forever_stops_on_cancel(self):
        """run_forever exits on CancelledError."""
        queue, _ = _make_queue()

        async def run():
            with patch.object(queue, "run_once", AsyncMock(return_value=False)):
                with pytest.raises(asyncio.CancelledError):
                    task = asyncio.create_task(queue.run_forever(poll_interval=0.01))
                    await asyncio.sleep(0.02)
                    task.cancel()
                    await task

        asyncio.run(run())

    def test_exhausted_retry_emits_single_terminal_failure(self):
        events = FakeEventRepository()

        def handler(_job):
            raise RuntimeError("final boom")

        queue = WorkerQueue(handler=handler, event_repository=events)
        fake_job = MagicMock(id="job-final", run_id="run-final")
        fake_job.id = "job-final"
        fake_job.run_id = "run-final"
        fake_job.attempt_count = 3
        fake_job.max_attempts = 3

        async def run():
            with patch.object(queue, "claim_next", AsyncMock(return_value=fake_job)):
                with patch.object(queue, "fail", AsyncMock()):
                    with patch.object(queue, "_set_run_status", AsyncMock()):
                        await queue.run_once()

        asyncio.run(run())
        assert len(events.events) == 1
        assert events.events[0].type.value == "run.failed"

    def test_paused_handler_result_is_not_overwritten_completed(self):
        async def handler(_job):
            return RunStatus.paused

        queue = WorkerQueue(handler=handler)
        fake_job = MagicMock(id="job-paused", run_id="run-paused")
        fake_job.id = "job-paused"
        fake_job.run_id = "run-paused"
        fake_job.attempt_count = 1
        fake_job.max_attempts = 3

        async def run():
            with patch.object(queue, "claim_next", AsyncMock(return_value=fake_job)):
                with patch.object(queue, "complete", AsyncMock()):
                    with patch.object(queue, "_set_run_status", AsyncMock()) as set_status:
                        await queue.run_once()
                        set_status.assert_awaited_once_with("run-paused", RunStatus.running)

        asyncio.run(run())

    def test_heartbeat_loop_renews_until_stopped(self):
        queue, _ = _make_queue()
        queue.lease_seconds = 0.03

        async def run():
            stop = asyncio.Event()
            handler_task = asyncio.create_task(asyncio.sleep(3600))
            lease_lost = asyncio.Event()
            with patch.object(queue, "heartbeat", AsyncMock(return_value=True)) as heartbeat:
                task = asyncio.create_task(
                    queue._heartbeat_loop("job-1", stop, handler_task, lease_lost)
                )
                await asyncio.sleep(1.05)
                stop.set()
                await task
                heartbeat.assert_awaited()
            handler_task.cancel()

        asyncio.run(run())

    def test_heartbeat_loss_cancels_handler(self):
        """When the lease is taken over the handler is cancelled and no
        terminal state is written by this worker."""
        events = FakeEventRepository()
        started = []

        async def handler(_job):
            started.append(True)
            await asyncio.sleep(30)

        queue = WorkerQueue(handler=handler, event_repository=events, lease_seconds=0.05)
        fake_job = MagicMock(id="job-lease", run_id="run-lease")
        fake_job.id = "job-lease"
        fake_job.run_id = "run-lease"
        fake_job.attempt_count = 1
        fake_job.max_attempts = 3

        async def run():
            with patch.object(queue, "claim_next", AsyncMock(return_value=fake_job)):
                with patch.object(queue, "complete", AsyncMock()) as mock_complete:
                    with patch.object(queue, "fail", AsyncMock()) as mock_fail:
                        with patch.object(queue, "_set_run_status", AsyncMock()):
                            with patch.object(queue, "heartbeat", AsyncMock(return_value=False)):
                                result = await queue.run_once()
                                assert result is True
                                mock_complete.assert_not_called()
                                mock_fail.assert_not_called()

        asyncio.run(run())
        assert started == [True]

    def test_cancelled_handler_result_does_not_overwrite_terminal_status(self):
        async def handler(_job):
            return RunStatus.cancelled

        queue = WorkerQueue(handler=handler)
        fake_job = MagicMock(id="job-cancel", run_id="run-cancel")
        fake_job.id = "job-cancel"
        fake_job.run_id = "run-cancel"
        fake_job.attempt_count = 1
        fake_job.max_attempts = 3

        async def run():
            with patch.object(queue, "claim_next", AsyncMock(return_value=fake_job)):
                with patch.object(queue, "complete", AsyncMock()):
                    with patch.object(queue, "_set_run_status", AsyncMock()) as set_status:
                        assert await queue.run_once() is True
                        statuses = [call.args[1] for call in set_status.await_args_list]
                        assert RunStatus.completed not in statuses
                        assert statuses.count(RunStatus.running) == 1

        asyncio.run(run())

    def test_run_forever_survives_transient_claim_failure(self):
        queue, calls = _make_queue()
        queue.retry_delay_seconds = 0

        async def run():
            with patch.object(
                queue, "run_once",
                AsyncMock(side_effect=[RuntimeError("db down"), False]),
            ):
                task = asyncio.create_task(queue.run_forever(poll_interval=0.01))
                await asyncio.sleep(0.2)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task

        asyncio.run(run())

    def test_non_retryable_job_fails_immediately_without_retry_wait(self):
        """Deterministic failures burn no retry attempts and emit one terminal event."""
        from app.services.errors import JobNotRetryable

        events = FakeEventRepository()

        async def handler(_job):
            raise JobNotRetryable("model_error: invalid request payload")

        queue = WorkerQueue(handler=handler, event_repository=events)
        fake_job = MagicMock(id="job-det", run_id="run-det")
        fake_job.id = "job-det"
        fake_job.run_id = "run-det"
        fake_job.attempt_count = 1
        fake_job.max_attempts = 3

        async def run():
            with patch.object(queue, "claim_next", AsyncMock(return_value=fake_job)):
                with patch.object(queue, "fail", AsyncMock()) as mock_fail:
                    with patch.object(queue, "_fail_without_retry", AsyncMock()) as fail_now:
                        with patch.object(queue, "_set_run_status", AsyncMock()):
                            assert await queue.run_once() is True
                            mock_fail.assert_not_called()          # no retry_wait scheduling
                            fail_now.assert_awaited_once()

        asyncio.run(run())
        assert len(events.events) == 1
        assert events.events[0].type.value == "run.failed"
