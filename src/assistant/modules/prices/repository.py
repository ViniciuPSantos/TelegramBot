from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.modules.prices.models import PricePoint, TrackedProduct


class TrackedProductRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, product: TrackedProduct) -> TrackedProduct:
        self._session.add(product)
        await self._session.flush()
        return product

    async def add_point(self, point: PricePoint) -> None:
        self._session.add(point)

    async def get(self, product_id: int, *, chat_id: int) -> TrackedProduct | None:
        product = await self._session.get(TrackedProduct, product_id)
        if product is None or product.chat_id != chat_id:
            return None
        return product

    async def find_by_url(self, chat_id: int, url: str) -> TrackedProduct | None:
        stmt = select(TrackedProduct).where(
            TrackedProduct.chat_id == chat_id, TrackedProduct.url == url
        )
        return await self._session.scalar(stmt)

    async def count_by_chat(self, chat_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(TrackedProduct)
            .where(TrackedProduct.chat_id == chat_id)
        )
        return await self._session.scalar(stmt) or 0

    async def list_by_chat(self, chat_id: int) -> Sequence[TrackedProduct]:
        stmt = (
            select(TrackedProduct)
            .where(TrackedProduct.chat_id == chat_id)
            .order_by(TrackedProduct.created_at)
        )
        return (await self._session.scalars(stmt)).all()

    async def list_due(self, now: datetime, *, limit: int) -> Sequence[TrackedProduct]:
        stmt = (
            select(TrackedProduct)
            .where(TrackedProduct.next_check_at <= now)
            .order_by(TrackedProduct.next_check_at)
            .limit(limit)
        )
        return (await self._session.scalars(stmt)).all()

    async def delete(self, product: TrackedProduct) -> None:
        await self._session.execute(delete(PricePoint).where(PricePoint.product_id == product.id))
        await self._session.delete(product)
