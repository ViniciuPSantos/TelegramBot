from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import CallbackQuery, Update
from telegram.ext import ContextTypes

from assistant.modules.reminders import views
from assistant.modules.reminders.parser import ReminderParseError, parse_reminder
from assistant.modules.reminders.service import (
    ReminderNotFoundError,
    ReminderService,
    ReminderValidationError,
)
from assistant.modules.reminders.views import Action, ButtonPress, Source


class ReminderHandlers:
    """Adaptador entre o Telegram e o ReminderService"""

    def __init__(self, service: ReminderService, *, tz: ZoneInfo, default_hour: int) -> None:
        self._service = service
        self._tz = tz
        self._default_hour = default_hour

    async def create(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, chat = update.effective_message, update.effective_chat
        if message is None or chat is None:
            return

        raw = " ".join(context.args or [])
        if not raw:
            await message.reply_text(views.USAGE)
            return

        try:
            parsed = parse_reminder(
                raw, now=datetime.now(self._tz), default_hour=self._default_hour
            )
            reminder = await self._service.create(chat.id, parsed)
        except (ReminderParseError, ReminderValidationError) as exc:
            await message.reply_text(f"{exc}\n\n{views.USAGE}")
            return

        await message.reply_text(views.created_text(reminder, self._tz))

    async def list_pending(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, chat = update.effective_message, update.effective_chat
        if message is None or chat is None:
            return

        reminders = await self._service.list_pending(chat.id)
        await message.reply_text(
            views.pending_list_text(reminders, self._tz),
            reply_markup=views.pending_list_keyboard(reminders),
        )

    async def list_done(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, chat = update.effective_message, update.effective_chat
        if message is None or chat is None:
            return

        reminders = await self._service.list_done(chat.id)
        await message.reply_text(views.done_list_text(reminders, self._tz))

    async def on_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query, chat = update.callback_query, update.effective_chat
        if query is None or chat is None or context.match is None:
            return

        press = views.parse_callback(context.match.groups())
        try:
            feedback = await self._apply(press, chat.id, query)
        except ReminderNotFoundError:
            feedback = "Esse lembrete não existe mais."
            if press.source is Source.LIST:
                await self._refresh_list(query, chat.id)
            else:
                await query.edit_message_reply_markup(reply_markup=None)
        except ReminderValidationError as exc:
            feedback = str(exc)

        # Todo callback precisa de answer(), senão o botão fica "carregando" no app.
        await query.answer(feedback)

    async def _apply(self, press: ButtonPress, chat_id: int, query: CallbackQuery) -> str:
        match press.action:
            case Action.DONE:
                reminder = await self._service.complete(chat_id, press.reminder_id)
                if press.source is Source.NOTIFICATION:
                    await query.edit_message_text(views.done_text(reminder))
                feedback = "Concluído!"
            case Action.DELETE:
                await self._service.delete(chat_id, press.reminder_id)
                feedback = "Apagado."
            case Action.SNOOZE:
                reminder = await self._service.snooze(chat_id, press.reminder_id)
                await query.edit_message_text(views.snoozed_text(reminder, self._tz))
                feedback = "Adiado por 1h."

        if press.source is Source.LIST:
            await self._refresh_list(query, chat_id)
        return feedback

    async def _refresh_list(self, query: CallbackQuery, chat_id: int) -> None:
        reminders = await self._service.list_pending(chat_id)
        await query.edit_message_text(
            views.pending_list_text(reminders, self._tz),
            reply_markup=views.pending_list_keyboard(reminders),
        )
