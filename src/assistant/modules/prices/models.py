from datetime import UTC, datetime

from sqlalchemy import BigInteger, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from assistant.db.base import Base
from assistant.db.types import UTCDateTime

URL_MAX_LENGTH = 1000
TITLE_MAX_LENGTH = 300
STORE_MAX_LENGTH = 50


class TrackedProduct(Base):
    __tablename__ = "tracked_products"
    __table_args__ = (
        UniqueConstraint("chat_id", "url"),
        Index("ix_tracked_products_next_check_at", "next_check_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    url: Mapped[str] = mapped_column(String(URL_MAX_LENGTH))
    store: Mapped[str] = mapped_column(String(STORE_MAX_LENGTH))
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH))

    target_cents: Mapped[int | None]
    target_alerted: Mapped[bool] = mapped_column(default=False)

    last_price_cents: Mapped[int]
    lowest_price_cents: Mapped[int]
    in_stock: Mapped[bool]

    last_checked_at: Mapped[datetime] = mapped_column(UTCDateTime())
    next_check_at: Mapped[datetime] = mapped_column(UTCDateTime())
    consecutive_failures: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=lambda: datetime.now(UTC))


class PricePoint(Base):
    __tablename__ = "price_points"
    __table_args__ = (Index("ix_price_points_product_id_checked_at", "product_id", "checked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("tracked_products.id", ondelete="CASCADE"))
    price_cents: Mapped[int]
    in_stock: Mapped[bool]
    checked_at: Mapped[datetime] = mapped_column(UTCDateTime())
