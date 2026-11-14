from collections.abc import AsyncIterator
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, insert, select
from sqlalchemy.exc import StatementError
from sqlalchemy.ext.asyncio import AsyncConnection

from assistant.db.engine import create_engine
from assistant.db.types import UTCDateTime

SP = ZoneInfo("America/Sao_Paulo")

metadata = MetaData()
events = Table(
    "events",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("at", UTCDateTime()),
)


@pytest.fixture
async def conn() -> AsyncIterator[AsyncConnection]:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
        yield connection
    await engine.dispose()


async def test_stores_and_returns_utc(conn: AsyncConnection) -> None:
    await conn.execute(insert(events).values(at=datetime(2026, 11, 12, 10, 0, tzinfo=SP)))

    stored = (await conn.execute(select(events.c.at))).scalar_one()

    assert stored == datetime(2026, 11, 12, 13, 0, tzinfo=UTC)
    assert stored.tzinfo == UTC


async def test_rejects_naive_datetime(conn: AsyncConnection) -> None:
    with pytest.raises(StatementError, match="sem timezone"):
        await conn.execute(insert(events).values(at=datetime(2026, 11, 12, 10, 0)))
