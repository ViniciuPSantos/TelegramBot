from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.modules.reminders.models import Reminder, ReminderStatus


class ReminderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, reminder: Reminder) -> Reminder:
        self._session.add(reminder)
        await self._session.flush()
        return reminder

    async def get(self, reminder_id: int, *, chat_id: int) -> Reminder | None:
        reminder = await self._session.get(Reminder, reminder_id)
        if reminder is None or reminder.chat_id != chat_id:
            return None
        return reminder

    async def delete(self, reminder: Reminder) -> None:
        await self._session.delete(reminder)

    async def list_pending(self, chat_id: int) -> Sequence[Reminder]:
        stmt = (
            select(Reminder)
            .where(Reminder.chat_id == chat_id, Reminder.status == ReminderStatus.PENDING)
            .order_by(Reminder.due_at)
        )
        return (await self._session.scalars(stmt)).all()

    async def list_done(self, chat_id: int, *, limit: int) -> Sequence[Reminder]:
        stmt = (
            select(Reminder)
            .where(Reminder.chat_id == chat_id, Reminder.status == ReminderStatus.DONE)
            .order_by(Reminder.completed_at.desc())
            .limit(limit)
        )
        return (await self._session.scalars(stmt)).all()

    async def list_due(self, now: datetime) -> Sequence[Reminder]:
        """Pendentes cujo horário chegou e o aviso ainda não foi enviado."""
        stmt = (
            select(Reminder)
            .where(
                Reminder.status == ReminderStatus.PENDING,
                Reminder.due_sent_at.is_(None),
                Reminder.due_at <= now,
            )
            .order_by(Reminder.due_at)
        )
        return (await self._session.scalars(stmt)).all()

    async def list_advance_due(self, now: datetime) -> Sequence[Reminder]:
        """Pendentes cujo aviso antecipado chegou e ainda não foi enviado."""
        stmt = (
            select(Reminder)
            .where(
                Reminder.status == ReminderStatus.PENDING,
                Reminder.advance_sent_at.is_(None),
                Reminder.advance_at <= now,
            )
            .order_by(Reminder.advance_at)
        )
        return (await self._session.scalars(stmt)).all()
