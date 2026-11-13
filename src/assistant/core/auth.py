import logging

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes, TypeHandler

logger = logging.getLogger(__name__)


def build_auth_handler(allowed_chat_id: int) -> TypeHandler:
    """Bloqueia qualquer update que não venha do chat autorizado.
    Deve ser registrado com group=-1 para rodar antes de todos os outros handlers.
    """

    async def check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        if chat is not None and chat.id == allowed_chat_id:
            return
        user = update.effective_user
        logger.warning(
            "acesso negado",
            extra={
                "chat_id": chat.id if chat else None,
                "user_id": user.id if user else None,
                "username": user.username if user else None,
            },
        )
        raise ApplicationHandlerStop

    return TypeHandler(Update, check)
