import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from assistant.core.formatting import format_datetime, truncate
from assistant.modules.reminders import views
from assistant.modules.reminders.models import Reminder
from assistant.modules.reminders.service import Notification, NotificationKind
from assistant.modules.reminders.views import Action, ButtonPress, Source

SP = ZoneInfo("America/Sao_Paulo")


def make_reminder(reminder_id: int = 1, text: str = "pagar fatura", **kwargs: object) -> Reminder:
    defaults: dict[str, object] = {"due_at": datetime(2026, 11, 15, 12, 0, tzinfo=UTC)}
    return Reminder(id=reminder_id, chat_id=42, text=text, **(defaults | kwargs))


def test_format_datetime_converts_to_user_timezone() -> None:
    assert format_datetime(datetime(2026, 11, 15, 12, 0, tzinfo=UTC), SP) == "dom 15/11/2026 09:00"


def test_truncate_adds_ellipsis_only_when_needed() -> None:
    assert truncate("curto", 10) == "curto"
    assert truncate("um texto bem comprido", 10) == "um texto …"


def test_callback_data_round_trip() -> None:
    data = views.callback_data(Source.LIST, Action.DELETE, 123)
    match = re.match(views.CALLBACK_PATTERN, data)

    assert match is not None
    assert views.parse_callback(match.groups()) == ButtonPress(Source.LIST, Action.DELETE, 123)
    assert len(data.encode()) <= 64  # limite do Telegram


def test_pending_list_numbers_items_and_has_one_button_row_each() -> None:
    reminders = [make_reminder(1, "dentista"), make_reminder(2, "academia")]

    text = views.pending_list_text(reminders, SP)
    keyboard = views.pending_list_keyboard(reminders)

    assert "1. dom 15/11/2026 09:00: dentista" in text
    assert "2. dom 15/11/2026 09:00: academia" in text
    assert keyboard is not None
    assert len(keyboard.inline_keyboard) == 2


def test_empty_pending_list_has_no_keyboard() -> None:
    assert "Nenhum" in views.pending_list_text([], SP)
    assert views.pending_list_keyboard([]) is None


def test_late_due_notification_has_warning_and_snooze_button() -> None:
    notification = Notification(make_reminder(), NotificationKind.DUE, late=True)

    text = views.notification_text(notification, SP)
    [buttons] = views.notification_keyboard(notification).inline_keyboard

    assert text.startswith("⚠️ Atrasado!")
    assert [b.text for b in buttons] == ["✅ Feito", "⏰ Adiar 1h"]


def test_advance_notification_has_no_snooze_button() -> None:
    reminder = make_reminder(days_before=3)
    notification = Notification(reminder, NotificationKind.ADVANCE, late=False)

    text = views.notification_text(notification, SP)
    [buttons] = views.notification_keyboard(notification).inline_keyboard

    assert text.startswith("🔔 Daqui a 3 dia(s):")
    assert [b.text for b in buttons] == ["✅ Feito"]
