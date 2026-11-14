import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot

from assistant.modules.reminders import views
from assistant.modules.reminders.service import Notification, Notifier, ReminderService

logger = logging.getLogger(__name__)

DISPATCH_JOB_ID = "reminders.dispatch"


class TelegramNotifier:
    def __init__(self, bot: Bot, tz: ZoneInfo) -> None:
        self._bot = bot
        self._tz = tz

    async def notify(self, notification: Notification) -> None:
        await self._bot.send_message(
            chat_id=notification.reminder.chat_id,
            text=views.notification_text(notification, self._tz),
            reply_markup=views.notification_keyboard(notification),
        )


def schedule_dispatch(
    scheduler: AsyncIOScheduler,
    service: ReminderService,
    notifier: Notifier,
    *,
    interval_seconds: int,
) -> None:
    async def dispatch() -> None:
        try:
            sent = await service.dispatch_due(notifier)
        except Exception:
            logger.exception("falha no job de lembretes")
            return
        if sent:
            logger.info("avisos enviados", extra={"count": sent})

    scheduler.add_job(
        dispatch,
        "interval",
        seconds=interval_seconds,
        id=DISPATCH_JOB_ID,
        replace_existing=True,
        # Roda logo ao subir, para enviar o que venceu com o bot offline.
        next_run_time=datetime.now(UTC),
        # Se uma execução atrasar, não empilha outras em paralelo.
        max_instances=1,
        coalesce=True,
        # Sem isso, execuções com mais de 1s de atraso (ex.: a subida do bot) são descartadas.
        misfire_grace_time=None,
    )
