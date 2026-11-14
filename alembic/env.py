import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from assistant.config import Settings
from assistant.db import models  # noqa: F401  (registra os models no metadata)
from assistant.db.base import Base
from assistant.db.engine import create_engine
from assistant.db.types import UTCDateTime

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Permite que testes passem a URL direto; senão usa a do .env.
# O % precisa ser escapado porque o alembic.ini usa interpolação estilo configparser.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", Settings().database_url.replace("%", "%%"))

target_metadata = Base.metadata


def render_item(type_: str, obj: object, autogen_context: object) -> str | bool:
    """Grava UTCDateTime como DateTime comum, para as migrations não importarem código da app."""
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_engine(config.get_main_option("sqlalchemy.url") or "")
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
