from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Enum, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from assistant.db.base import Base
from assistant.db.types import UTCDateTime

TEXT_MAX_LENGTH = 500


class ReminderStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (
        Index("ix_reminders_status_due_at", "status", "due_at"),
        Index("ix_reminders_status_advance_at", "status", "advance_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    text: Mapped[str] = mapped_column(String(TEXT_MAX_LENGTH))
    status: Mapped[ReminderStatus] = mapped_column(
        Enum(ReminderStatus, native_enum=False, length=20),
        default=ReminderStatus.PENDING,
    )

    due_at: Mapped[datetime] = mapped_column(UTCDateTime())
    due_sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    days_before: Mapped[int | None]
    advance_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    advance_sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
