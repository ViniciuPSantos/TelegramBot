import logging

from telegram import Update
from telegram.error import NetworkError
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

FRIENDLY_ERROR = (
    "😕 Algo deu errado ao processar seu comando. Tente novamente em instantes."
)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error

    # Falhas de rede são transitórias: o PTB tenta de novo sozinho, então
    # um traceback completo seria só ruído no log.
    if isinstance(error, NetworkError):
        logger.warning("falha de rede com o Telegram: %s", error)
        return

    logger.error("erro não tratado", exc_info=error)

    if isinstance(update, Update) and update.effective_message is not None:
        await update.effective_message.reply_text(FRIENDLY_ERROR)
