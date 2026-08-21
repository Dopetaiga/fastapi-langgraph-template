from logging.config import fileConfig
from sqlalchemy import pool
from alembic import context

from app.db.engine import engine
from app.db.base import Base
from app.core.config import settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = settings.async_database_url
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    import asyncio

    async def do_run() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(context.configure, connection=conn, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()

    asyncio.run(do_run())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
