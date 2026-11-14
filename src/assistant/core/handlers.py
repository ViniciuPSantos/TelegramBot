from telegram import BotCommand, Update
from telegram.ext import ContextTypes

WELCOME_TEXT = (
    "👋 Olá! Sou seu assistente pessoal.\n\n"
    "📌 Lembretes\n"
    "/lembrete <data> [hora] <texto> [--antes N]: cria um lembrete\n"
    "   ex.: /lembrete amanha 10:00 dentista\n"
    "   ex.: /lembrete 15/11 pagar fatura --antes 3\n"
    "/lembretes: lista os pendentes\n"
    "/concluidos: últimos 10 concluídos"
)

BOT_COMMANDS = [
    BotCommand("start", "Boas-vindas e lista de comandos"),
    BotCommand("lembrete", "Cria um lembrete"),
    BotCommand("lembretes", "Lista os lembretes pendentes"),
    BotCommand("concluidos", "Ultimos lembretes concluidos"),
]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is None:
        return
    await update.effective_message.reply_text(WELCOME_TEXT)
