import logging

from telegram import Update
from telegram.ext import Application, CommandHandler

from assistant.config import Settings
from assistant.core.auth import build_auth_handler
from assistant.core.errors import error_handler
from assistant.core.handlers import start
from assistant.logging_config import setup_logging

logger = logging.getLogger(__name__)


def build_application(settings: Settings) -> Application:
    app = Application.builder().token(settings.telegram_bot_token.get_secret_value()).build()

    app.add_handler(build_auth_handler(settings.allowed_chat_id), group=-1)
    app.add_handler(CommandHandler("start", start))
    app.add_error_handler(error_handler)

    return app


def main() -> None:
    settings = Settings()
    setup_logging(settings.log_level, settings.log_format)

    app = build_application(settings)
    logger.info("bot iniciando", extra={"timezone": settings.timezone})
    app.run_polling(allowed_updates=Update.ALL_TYPES)
