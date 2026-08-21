"""Tests for WorkerQueue (Phase 7)."""
from __future__ import annotations

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.runtime.worker import WorkerQueue


def _make_queue():
    calls = []
    def handler(job):
        calls.append(job)
    return WorkerQueue(handler=handler), calls


class TestWorkerQueueInterface:
    def test_handler_receives_job(self):
        """run_once passes claimed job to handler."""
        queue, calls = _make_queue()
        fake_job = MagicMock()
        fake_job.id = "job-1"
        fake_job.run_id = "run-1"

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
        queue, calls = _make_queue()
        fake_job = MagicMock()
        fake_job.id = "job-err"
        fake_job.run_id = "run-err"

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
