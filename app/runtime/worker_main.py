"""Standalone PostgreSQL worker process entrypoint."""
from __future__ import annotations

import asyncio

from app.core.config import settings
from app.runtime.run_manager import RunManager
from app.runtime.worker import WorkerQueue
from app.tools.bootstrap import build_tool_registry


async def run_worker() -> None:
    registry = await build_tool_registry(
        mcp_endpoints=settings.mcp_endpoints,
        openapi_urls=settings.openapi_urls,
    )
    manager = RunManager(graphs_dir="graphs", tool_registry=registry)
    queue = WorkerQueue(handler=manager.execute_job)
    await queue.run_forever()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":  # pragma: no cover
    main()
