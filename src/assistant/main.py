import logging
from collections.abc import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import Application, CommandHandler, filters

from assistant.config import Settings
from assistant.core.auth import build_auth_handler
from assistant.core.context import AppContext
from assistant.core.errors import error_handler
from assistant.core.handlers import start
from assistant.db.engine import create_engine, create_session_factory
from assistant.logging_config import setup_logging
from assistant.modules.reminders import module as reminders

logger = logging.getLogger(__name__)

ModuleRegistrar = Callable[[Application, AppContext], None]


MODULES: list[ModuleRegistrar] = [reminders.register]


def build_context(settings: Settings) -> AppContext:
    engine = create_engine(settings.database_url)
    return AppContext(
        settings=settings,
        engine=engine,
        session_factory=create_session_factory(engine),
        scheduler=AsyncIOScheduler(timezone=settings.tz),
    )


def build_application(ctx: AppContext) -> Application:
    settings = ctx.settings
    app = (
        Application.builder()
        .token(settings.telegram_bot_token.get_secret_value())
        .post_init(ctx.startup)
        .post_shutdown(ctx.shutdown)
        .build()
    )

    app.add_handler(build_auth_handler(settings.allowed_chat_id), group=-1)
    app.add_handler(CommandHandler("start", start, filters=filters.UpdateType.MESSAGE))
    for register in MODULES:
        register(app, ctx)
    app.add_error_handler(error_handler)

    return app


def main() -> None:
    settings = Settings()
    setup_logging(settings.log_level, settings.log_format)

    app = build_application(build_context(settings))
    logger.info("bot iniciando", extra={"timezone": settings.timezone})
    app.run_polling(allowed_updates=Update.ALL_TYPES)
