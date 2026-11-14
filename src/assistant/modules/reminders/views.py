from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from assistant.core.formatting import format_datetime, truncate
from assistant.modules.reminders.models import Reminder
from assistant.modules.reminders.service import Notification, NotificationKind

USAGE = (
    "Uso: /lembrete <data> [hora] <texto> [--antes N]\n\n"
    "Exemplos:\n"
    "/lembrete 15/11 pagar fatura\n"
    "/lembrete 15/11 14:30 reunião\n"
    "/lembrete amanha 10:00 dentista\n"
    "/lembrete hoje 18:00 academia\n"
    "/lembrete 10/12 pagar IPVA --antes 3"
)

LIST_TEXT_MAX_LENGTH = 60
LIST_MAX_ITEMS = 20

CALLBACK_PATTERN = r"^rem:(l|n):(done|del|snooze):(\d+)$"


class Source(StrEnum):
    LIST = "l"
    NOTIFICATION = "n"


class Action(StrEnum):
    DONE = "done"
    DELETE = "del"
    SNOOZE = "snooze"


@dataclass(frozen=True, slots=True)
class ButtonPress:
    source: Source
    action: Action
    reminder_id: int


def callback_data(source: Source, action: Action, reminder_id: int) -> str:
    return f"rem:{source}:{action}:{reminder_id}"


def parse_callback(groups: Sequence[str]) -> ButtonPress:
    source, action, reminder_id = groups
    return ButtonPress(Source(source), Action(action), int(reminder_id))


# ------criacao---------------------------------------------------------------------------


def created_text(reminder: Reminder, tz: ZoneInfo) -> str:
    lines = ["Lembrete criado!", f"{reminder.text}", f"{format_datetime(reminder.due_at, tz)}"]
    if reminder.advance_at is not None:
        when = format_datetime(reminder.advance_at, tz)
        lines.append(f"Aviso antecipado: {reminder.days_before} dia(s) antes ({when})")
    elif reminder.days_before is not None:
        lines.append(
            f"⚠️ O aviso de {reminder.days_before} dia(s) antes já passou; vou avisar só no horário."
        )
    return "\n".join(lines)


# ------listagem---------------------------------------------------------------------------


def pending_list_text(reminders: Sequence[Reminder], tz: ZoneInfo) -> str:
    if not reminders:
        return "Nenhum lembrete pendente."

    lines = ["Lembretes pendentes:", ""]
    for number, reminder in enumerate(reminders[:LIST_TEXT_MAX_LENGTH], start=1):
        text = truncate(reminder.text, LIST_TEXT_MAX_LENGTH)
        advance = f"{reminder.days_before}d" if reminder.advance_at is not None else ""
        lines.append(f"{number}. {format_datetime(reminder.due_at, tz)}: {text}{advance}")

    hidden = len(reminders) - LIST_MAX_ITEMS
    if hidden > 0:
        lines.append(f"\n... e mais {hidden} lembrete(s)")
    return "\n".join(lines)


def pending_list_keyboard(reminders: Sequence[Reminder]) -> InlineKeyboardMarkup | None:
    if not reminders:
        return None
    rows = [
        [
            InlineKeyboardButton(
                f"✅ Concluir {number}",
                callback_data=callback_data(Source.LIST, Action.DONE, reminder.id),
            ),
            InlineKeyboardButton(
                f"🗑 Apagar {number}",
                callback_data=callback_data(Source.LIST, Action.DELETE, reminder.id),
            ),
        ]
        for number, reminder in enumerate(reminders[:LIST_MAX_ITEMS], start=1)
    ]
    return InlineKeyboardMarkup(rows)


def done_list_text(reminders: Sequence[Reminder], tz: ZoneInfo) -> str:
    if not reminders:
        return "Nenhum lembrete concluído ainda."

    lines = ["✅ Últimos concluídos:", ""]
    for reminder in reminders:
        text = truncate(reminder.text, LIST_TEXT_MAX_LENGTH)
        completed = format_datetime(reminder.completed_at, tz) if reminder.completed_at else "?"
        lines.append(f"• {text} (em {completed})")
    return "\n".join(lines)


# ---- avisos ----------------------------------------------------------------


def notification_text(notification: Notification, tz: ZoneInfo) -> str:
    reminder = notification.reminder
    when = format_datetime(reminder.due_at, tz)

    if notification.kind is NotificationKind.ADVANCE:
        header = f"🔔 Daqui a {reminder.days_before} dia(s):"
    else:
        header = "⏰ Lembrete:"
    if notification.late:
        header = f"⚠️ Atrasado! {header}"

    return f"{header} {reminder.text}\n🗓 {when}"


def notification_keyboard(notification: Notification) -> InlineKeyboardMarkup:
    reminder_id = notification.reminder.id
    buttons = [
        InlineKeyboardButton(
            "✅ Feito", callback_data=callback_data(Source.NOTIFICATION, Action.DONE, reminder_id)
        )
    ]
    # Adiar só faz sentido no aviso do horário; no antecipado ainda falta tempo.
    if notification.kind is NotificationKind.DUE:
        buttons.append(
            InlineKeyboardButton(
                "⏰ Adiar 1h",
                callback_data=callback_data(Source.NOTIFICATION, Action.SNOOZE, reminder_id),
            )
        )
    return InlineKeyboardMarkup([buttons])


def done_text(reminder: Reminder) -> str:
    return f"✅ Feito: {reminder.text}"


def snoozed_text(reminder: Reminder, tz: ZoneInfo) -> str:
    return f"⏰ Adiado para {format_datetime(reminder.due_at, tz)}: {reminder.text}"
