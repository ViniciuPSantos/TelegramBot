from telegram.ext import Application, CallbackQueryHandler, CommandHandler, filters

from assistant.core.context import AppContext
from assistant.modules.reminders.handlers import ReminderHandlers
from assistant.modules.reminders.jobs import TelegramNotifier, schedule_dispatch
from assistant.modules.reminders.service import ReminderService
from assistant.modules.reminders.views import CALLBACK_PATTERN


def register(app: Application, ctx: AppContext) -> None:
    settings = ctx.settings
    service = ReminderService(ctx.session_factory)
    handlers = ReminderHandlers(
        service, tz=settings.tz, default_hour=settings.reminder_default_hour
    )

    new_messages = filters.UpdateType.MESSAGE

    app.add_handler(CommandHandler("lembrete", handlers.create, filters=new_messages))
    app.add_handler(CommandHandler("lembretes", handlers.list_pending, filters=new_messages))
    app.add_handler(CommandHandler("concluidos", handlers.list_done, filters=new_messages))
    app.add_handler(CallbackQueryHandler(handlers.on_button, pattern=CALLBACK_PATTERN))

    schedule_dispatch(
        ctx.scheduler,
        service,
        TelegramNotifier(app.bot, settings.tz),
        interval_seconds=settings.reminder_poll_seconds,
    )
