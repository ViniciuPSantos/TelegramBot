from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from assistant.db import models  # noqa: F401  (registra os models no metadata)
from assistant.db.base import Base
from assistant.modules.reminders.models import ReminderStatus
from assistant.modules.reminders.parser import ParsedReminder
from assistant.modules.reminders.service import (
    Notification,
    NotificationKind,
    ReminderNotFoundError,
    ReminderService,
    ReminderValidationError,
)

SP = ZoneInfo("America/Sao_Paulo")
CHAT_ID = 42
OTHER_CHAT_ID = 99


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[Notification] = []
        self.fail = False

    async def notify(self, notification: Notification) -> None:
        if self.fail:
            raise RuntimeError("Telegram fora do ar")
        self.sent.append(notification)


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # StaticPool: todas as sessões usam a mesma conexão, então enxergam o mesmo banco em memória.
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 11, 12, 13, 0, tzinfo=UTC))  # 10:00 em São Paulo


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
def service(session_factory: async_sessionmaker[AsyncSession], clock: FakeClock) -> ReminderService:
    return ReminderService(session_factory, clock=clock)


def parsed(
    text: str = "pagar fatura",
    *,
    due_at: datetime = datetime(2026, 11, 15, 9, 0, tzinfo=SP),
    days_before: int | None = None,
) -> ParsedReminder:
    return ParsedReminder(due_at=due_at, text=text, days_before=days_before)


# ---- criar -----------------------------------------------------------------


async def test_create_stores_pending_reminder_in_utc(service: ReminderService) -> None:
    reminder = await service.create(CHAT_ID, parsed())

    assert reminder.id is not None
    assert reminder.status == ReminderStatus.PENDING
    assert reminder.due_at == datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    assert reminder.advance_at is None


async def test_create_computes_advance_at(service: ReminderService) -> None:
    reminder = await service.create(CHAT_ID, parsed(days_before=2))

    assert reminder.days_before == 2
    assert reminder.advance_at == datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


async def test_create_drops_advance_already_in_the_past(service: ReminderService) -> None:
    # vence em 3 dias; avisar 5 dias antes cairia no passado
    reminder = await service.create(CHAT_ID, parsed(days_before=5))

    assert reminder.days_before == 5
    assert reminder.advance_at is None


async def test_create_rejects_text_too_long(service: ReminderService) -> None:
    with pytest.raises(ReminderValidationError, match="no máximo"):
        await service.create(CHAT_ID, parsed("x" * 501))


# ---- listar ----------------------------------------------------------------


async def test_list_pending_is_ordered_by_due_date(service: ReminderService) -> None:
    await service.create(CHAT_ID, parsed("depois", due_at=datetime(2026, 11, 20, 9, 0, tzinfo=SP)))
    await service.create(CHAT_ID, parsed("antes", due_at=datetime(2026, 11, 14, 9, 0, tzinfo=SP)))
    await service.create(OTHER_CHAT_ID, parsed("de outro chat"))

    pending = await service.list_pending(CHAT_ID)

    assert [r.text for r in pending] == ["antes", "depois"]


async def test_list_done_returns_most_recent_first_limited_to_10(
    service: ReminderService, clock: FakeClock
) -> None:
    for i in range(12):
        reminder = await service.create(CHAT_ID, parsed(f"lembrete {i}"))
        await service.complete(CHAT_ID, reminder.id)
        clock.advance(timedelta(minutes=1))

    done = await service.list_done(CHAT_ID)

    assert len(done) == 10
    assert done[0].text == "lembrete 11"
    assert done[-1].text == "lembrete 2"


# ---- concluir / apagar / adiar ---------------------------------------------


async def test_complete_marks_as_done(service: ReminderService, clock: FakeClock) -> None:
    reminder = await service.create(CHAT_ID, parsed())

    done = await service.complete(CHAT_ID, reminder.id)

    assert done.status == ReminderStatus.DONE
    assert done.completed_at == clock.now
    assert await service.list_pending(CHAT_ID) == []


async def test_complete_from_another_chat_is_not_found(service: ReminderService) -> None:
    reminder = await service.create(CHAT_ID, parsed())

    with pytest.raises(ReminderNotFoundError):
        await service.complete(OTHER_CHAT_ID, reminder.id)


async def test_delete_removes_reminder(service: ReminderService) -> None:
    reminder = await service.create(CHAT_ID, parsed())

    await service.delete(CHAT_ID, reminder.id)

    assert await service.list_pending(CHAT_ID) == []
    with pytest.raises(ReminderNotFoundError):
        await service.delete(CHAT_ID, reminder.id)


async def test_snooze_moves_due_date_one_hour_from_now(
    service: ReminderService, clock: FakeClock
) -> None:
    reminder = await service.create(CHAT_ID, parsed())

    snoozed = await service.snooze(CHAT_ID, reminder.id)

    assert snoozed.due_at == clock.now + timedelta(hours=1)
    assert snoozed.due_sent_at is None


async def test_snooze_rejects_done_reminder(service: ReminderService) -> None:
    reminder = await service.create(CHAT_ID, parsed())
    await service.complete(CHAT_ID, reminder.id)

    with pytest.raises(ReminderValidationError):
        await service.snooze(CHAT_ID, reminder.id)


# ---- envio dos avisos ------------------------------------------------------


async def test_dispatch_sends_nothing_before_due_time(
    service: ReminderService, notifier: FakeNotifier
) -> None:
    await service.create(CHAT_ID, parsed())

    assert await service.dispatch_due(notifier) == 0
    assert notifier.sent == []


async def test_dispatch_sends_due_reminder_only_once(
    service: ReminderService, clock: FakeClock, notifier: FakeNotifier
) -> None:
    reminder = await service.create(CHAT_ID, parsed())
    clock.now = reminder.due_at

    assert await service.dispatch_due(notifier) == 1
    assert await service.dispatch_due(notifier) == 0

    [notification] = notifier.sent
    assert notification.kind is NotificationKind.DUE
    assert notification.late is False


async def test_dispatch_flags_overdue_reminder_as_late(
    service: ReminderService, clock: FakeClock, notifier: FakeNotifier
) -> None:
    reminder = await service.create(CHAT_ID, parsed())
    clock.now = reminder.due_at + timedelta(hours=3)  # bot ficou offline

    await service.dispatch_due(notifier)

    assert notifier.sent[0].late is True


async def test_dispatch_sends_advance_then_due(
    service: ReminderService, clock: FakeClock, notifier: FakeNotifier
) -> None:
    reminder = await service.create(CHAT_ID, parsed(days_before=2))

    assert reminder.advance_at is not None
    clock.now = reminder.advance_at
    await service.dispatch_due(notifier)
    clock.now = reminder.due_at
    await service.dispatch_due(notifier)

    assert [n.kind for n in notifier.sent] == [NotificationKind.ADVANCE, NotificationKind.DUE]


async def test_dispatch_skips_advance_when_due_time_already_passed(
    service: ReminderService, clock: FakeClock, notifier: FakeNotifier
) -> None:
    reminder = await service.create(CHAT_ID, parsed(days_before=2))
    clock.now = reminder.due_at + timedelta(days=1)

    await service.dispatch_due(notifier)
    await service.dispatch_due(notifier)

    assert [n.kind for n in notifier.sent] == [NotificationKind.DUE]


async def test_dispatch_retries_when_sending_fails(
    service: ReminderService, clock: FakeClock, notifier: FakeNotifier
) -> None:
    reminder = await service.create(CHAT_ID, parsed())
    clock.now = reminder.due_at
    notifier.fail = True

    assert await service.dispatch_due(notifier) == 0

    notifier.fail = False
    assert await service.dispatch_due(notifier) == 1


async def test_dispatch_skips_completed_reminder(
    service: ReminderService, clock: FakeClock, notifier: FakeNotifier
) -> None:
    reminder = await service.create(CHAT_ID, parsed())
    await service.complete(CHAT_ID, reminder.id)
    clock.now = reminder.due_at

    assert await service.dispatch_due(notifier) == 0


async def test_snoozed_reminder_is_sent_again_after_one_hour(
    service: ReminderService, clock: FakeClock, notifier: FakeNotifier
) -> None:
    reminder = await service.create(CHAT_ID, parsed())
    clock.now = reminder.due_at
    await service.dispatch_due(notifier)

    await service.snooze(CHAT_ID, reminder.id)
    clock.advance(timedelta(minutes=59))
    assert await service.dispatch_due(notifier) == 0

    clock.advance(timedelta(minutes=1))
    assert await service.dispatch_due(notifier) == 1
