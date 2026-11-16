import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from assistant.core.clock import Clock, utc_now
from assistant.modules.reminders.models import TEXT_MAX_LENGTH, Reminder, ReminderStatus
from assistant.modules.reminders.parser import ParsedReminder
from assistant.modules.reminders.repository import ReminderRepository

logger = logging.getLogger(__name__)


DONE_LIST_LIMIT = 10
SNOOZE_DELTA = timedelta(hours=1)
LATE_TOLERANCE = timedelta(minutes=5)


class ReminderNotFoundError(Exception):
    """O lembrete nao existe (ou pertence a outro chat)"""


class ReminderValidationError(ValueError):
    """Regra de negocio violada. A mensagem e mostrada ao user"""


class NotificationKind(StrEnum):
    ADVANCE = "advance"
    DUE = "due"


@dataclass(frozen=True, slots=True)
class Notification:
    reminder: Reminder
    kind: NotificationKind
    late: bool


class Notifier(Protocol):
    async def notify(self, notification: Notification) -> None: ...


class ReminderService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Clock = utc_now,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    @asynccontextmanager
    async def _repository(self) -> AsyncIterator[ReminderRepository]:
        """Abre uma sessão com transação: commit ao sair, rollback se houver exceção."""
        async with self._session_factory() as session, session.begin():
            yield ReminderRepository(session)

    async def create(self, chat_id: int, parsed: ParsedReminder) -> Reminder:
        if len(parsed.text) > TEXT_MAX_LENGTH:
            raise ReminderValidationError(
                f"O texto do lembrete pode ter no máximo {TEXT_MAX_LENGTH} caracteres."
            )

        now = self._clock()
        due_at = parsed.due_at.astimezone(UTC)
        advance_at = None
        if parsed.days_before is not None:
            candidate = due_at - timedelta(days=parsed.days_before)
            # Se o aviso antecipado já ficou no passado, ele é descartado.
            if candidate > now:
                advance_at = candidate

        reminder = Reminder(
            chat_id=chat_id,
            text=parsed.text,
            due_at=due_at,
            days_before=parsed.days_before,
            advance_at=advance_at,
        )
        async with self._repository() as repo:
            await repo.add(reminder)

        logger.info("lembrete criado", extra={"reminder_id": reminder.id, "due_at": due_at})
        return reminder

    async def list_pending(self, chat_id: int) -> Sequence[Reminder]:
        async with self._repository() as repo:
            return await repo.list_pending(chat_id)

    async def list_done(self, chat_id: int) -> Sequence[Reminder]:
        async with self._repository() as repo:
            return await repo.list_done(chat_id, limit=DONE_LIST_LIMIT)

    async def complete(self, chat_id: int, reminder_id: int) -> Reminder:
        async with self._repository() as repo:
            reminder = await self._get_or_raise(repo, reminder_id, chat_id)
            if reminder.status != ReminderStatus.DONE:
                reminder.status = ReminderStatus.DONE
                reminder.completed_at = self._clock()
        return reminder

    async def delete(self, chat_id: int, reminder_id: int) -> None:
        async with self._repository() as repo:
            reminder = await self._get_or_raise(repo, reminder_id, chat_id)
            await repo.delete(reminder)

    async def snooze(self, chat_id: int, reminder_id: int) -> Reminder:
        async with self._repository() as repo:
            reminder = await self._get_or_raise(repo, reminder_id, chat_id)
            if reminder.status == ReminderStatus.DONE:
                raise ReminderValidationError("Esse lembrete já foi concluído.")
            reminder.due_at = self._clock() + SNOOZE_DELTA
            reminder.due_sent_at = None
        return reminder

    async def dispatch_due(self, notifier: Notifier) -> int:
        """Envia os avisos vencidos e devolve quantos foram enviados.

        Cada aviso só é marcado como enviado depois que o envio dá certo; se falhar,
        ele é tentado de novo no próximo ciclo (entrega "pelo menos uma vez").
        """
        now = self._clock()
        notifications: list[Notification] = []

        async with self._repository() as repo:
            for reminder in await repo.list_advance_due(now):
                advance_at = reminder.advance_at
                if advance_at is None or reminder.due_at <= now:
                    # O horário principal já chegou: o aviso antecipado perdeu o sentido.
                    reminder.advance_sent_at = now
                    continue
                late = now - advance_at > LATE_TOLERANCE
                notifications.append(Notification(reminder, NotificationKind.ADVANCE, late))

            for reminder in await repo.list_due(now):
                late = now - reminder.due_at > LATE_TOLERANCE
                notifications.append(Notification(reminder, NotificationKind.DUE, late))

        sent = 0
        for notification in notifications:
            try:
                await notifier.notify(notification)
            except Exception:
                logger.exception(
                    "falha ao enviar aviso", extra={"reminder_id": notification.reminder.id}
                )
                continue
            await self._mark_sent(notification, now)
            sent += 1
        return sent

    async def _mark_sent(self, notification: Notification, sent_at: datetime) -> None:
        reminder = notification.reminder
        async with self._repository() as repo:
            current = await repo.get(reminder.id, chat_id=reminder.chat_id)
            if current is None:
                return  # apagado enquanto o aviso era enviado
            if notification.kind is NotificationKind.ADVANCE:
                current.advance_sent_at = sent_at
            else:
                current.due_sent_at = sent_at

    @staticmethod
    async def _get_or_raise(repo: ReminderRepository, reminder_id: int, chat_id: int) -> Reminder:
        reminder = await repo.get(reminder_id, chat_id=chat_id)
        if reminder is None:
            raise ReminderNotFoundError(f"Lembrete {reminder_id} não encontrado.")
        return reminder
