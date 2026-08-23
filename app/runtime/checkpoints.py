"""LangGraph PostgreSQL checkpointer lifecycle helpers."""
from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.observability.telemetry import traced_span

if sys.platform == "win32":  # psycopg async does not support ProactorEventLoop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def psycopg_connection_string(sqlalchemy_url: str) -> str:
    """Convert the configured SQLAlchemy async URL to a psycopg URL."""
    return sqlalchemy_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@asynccontextmanager
async def postgres_checkpointer(database_url: str, *, setup: bool = False):
    """Open an AsyncPostgresSaver for one bounded worker execution."""
    connection_string = psycopg_connection_string(database_url)
    with traced_span("checkpoint.session", {"db.system": "postgresql"}):
        async with AsyncPostgresSaver.from_conn_string(connection_string) as saver:
            if setup:
                with traced_span("checkpoint.setup", {"db.system": "postgresql"}):
                    await saver.setup()
            yield saver
