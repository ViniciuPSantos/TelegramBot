from telegram.ext import Application, CallbackQueryHandler, CommandHandler, filters

from assistant.core.context import AppContext
from assistant.modules.prices.handlers import PriceHandlers
from assistant.modules.prices.http import build_http_client
from assistant.modules.prices.jobs import TelegramPriceNotifier, schedule_checks
from assistant.modules.prices.service import PriceService
from assistant.modules.prices.stores import build_sources
from assistant.modules.prices.views import CALLBACK_PATTERN


def register(app: Application, ctx: AppContext) -> None:
    client = build_http_client()
    ctx.on_shutdown(client.aclose)

    service = PriceService(ctx.session_factory, build_sources(client))
    handlers = PriceHandlers(service)

    new_messages = filters.UpdateType.MESSAGE

    app.add_handler(CommandHandler("monitorar", handlers.track, filters=new_messages))
    app.add_handler(CommandHandler("produtos", handlers.list_products, filters=new_messages))
    app.add_handler(CallbackQueryHandler(handlers.on_button, pattern=CALLBACK_PATTERN))
    schedule_checks(
        ctx.scheduler,
        service,
        TelegramPriceNotifier(app.bot),
        interval_minutes=ctx.settings.price_poll_minutes,
    )
