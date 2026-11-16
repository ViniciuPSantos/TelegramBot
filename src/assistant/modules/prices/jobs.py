import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot

from assistant.modules.prices import views
from assistant.modules.prices.service import PriceAlert, PriceNotifier, PriceService

logger = logging.getLogger(__name__)

CHECK_JOB_ID = "prices.check"


class TelegramPriceNotifier:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def notify(self, alert: PriceAlert) -> None:
        await self._bot.send_message(
            chat_id=alert.product.chat_id,
            text=views.alert_text(alert),
            reply_markup=views.alert_keyboard(alert),
        )


def schedule_checks(
    scheduler: AsyncIOScheduler,
    service: PriceService,
    notifier: PriceNotifier,
    *,
    interval_minutes: int,
) -> None:
    async def check() -> None:
        try:
            checked = await service.check_due(notifier)
        except Exception:
            logger.exception("falha no job de preços")
            return
        if checked:
            logger.info("preços verificados", extra={"count": checked})

    scheduler.add_job(
        check,
        "interval",
        minutes=interval_minutes,
        id=CHECK_JOB_ID,
        replace_existing=True,
        # Roda logo ao subir: o que venceu com o bot offline é verificado na hora.
        next_run_time=datetime.now(UTC),
        # Um lote tem pausas de 3 a 8s entre lojas: se demorar, não empilha execuções.
        max_instances=1,
        coalesce=True,
        misfire_grace_time=None,
    )
