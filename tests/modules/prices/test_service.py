import random
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from assistant.db import models  # noqa: F401  (registra os models no metadata)
from assistant.db.base import Base
from assistant.modules.prices.models import PricePoint
from assistant.modules.prices.rules import AlertKind
from assistant.modules.prices.service import (
    CHECK_INTERVAL,
    CHECK_JITTER,
    STORE_PAUSE,
    PriceAlert,
    PriceService,
    PriceValidationError,
    ProductNotFoundError,
)
from assistant.modules.prices.sources import (
    PriceFetchError,
    PriceQuote,
    StoreBlockedError,
    UnsupportedStoreError,
    host_matches,
)

CHAT_ID = 42
OTHER_CHAT_ID = 99
URL = "https://www.kabum.com.br/produto/1/ssd"
URL_2 = "https://www.kabum.com.br/produto/2/mouse"
URL_3 = "https://www.loja2.com.br/produto/3/teclado"


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


class FakeSource:
    """Loja falsa: devolve o que o teste programar para cada URL."""

    def __init__(self, name: str, domain: str) -> None:
        self.name = name
        self._domain = domain
        self.responses: dict[str, PriceQuote | PriceFetchError] = {}
        self.calls: list[str] = []

    def supports(self, url: str) -> bool:
        return host_matches(url, (self._domain,))

    async def fetch(self, url: str) -> PriceQuote:
        self.calls.append(url)
        response = self.responses[url]
        if isinstance(response, PriceFetchError):
            raise response
        return response


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[PriceAlert] = []
        self.fail = False

    async def notify(self, alert: PriceAlert) -> None:
        if self.fail:
            raise RuntimeError("Telegram fora do ar")
        self.sent.append(alert)


class FakeSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def quote(price: int, *, in_stock: bool = True) -> PriceQuote:
    return PriceQuote(title="SSD Kingston", price_cents=price, in_stock=in_stock)


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 11, 15, 12, 0, tzinfo=UTC))


@pytest.fixture
def kabum() -> FakeSource:
    source = FakeSource("Kabum", "kabum.com.br")
    source.responses = {URL: quote(100_00), URL_2: quote(50_00)}
    return source


@pytest.fixture
def loja2() -> FakeSource:
    source = FakeSource("Loja2", "loja2.com.br")
    source.responses = {URL_3: quote(200_00)}
    return source


@pytest.fixture
def sleep() -> FakeSleep:
    return FakeSleep()


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
def service(
    session_factory: async_sessionmaker[AsyncSession],
    kabum: FakeSource,
    loja2: FakeSource,
    clock: FakeClock,
    sleep: FakeSleep,
) -> PriceService:
    return PriceService(
        session_factory,
        [kabum, loja2],
        clock=clock,
        sleep=sleep,
        rng=random.Random(0),
        max_products=3,
    )


async def count_points(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(PricePoint)) or 0


def after_interval(clock: FakeClock) -> None:
    clock.advance(CHECK_INTERVAL + CHECK_JITTER)


# ---- track -----------------------------------------------------------------


async def test_track_saves_product_and_first_price(
    service: PriceService,
    clock: FakeClock,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    product = await service.track(CHAT_ID, f"  {URL}#avaliacoes ")

    assert product.url == URL  # sem espaços e sem o fragmento
    assert (product.store, product.title, product.last_price_cents) == (
        "Kabum",
        "SSD Kingston",
        100_00,
    )
    assert product.lowest_price_cents == 100_00
    low, high = clock.now + CHECK_INTERVAL - CHECK_JITTER, clock.now + CHECK_INTERVAL + CHECK_JITTER
    assert low <= product.next_check_at <= high
    assert await count_points(session_factory) == 1


async def test_track_rejects_unsupported_store(service: PriceService) -> None:
    with pytest.raises(UnsupportedStoreError):
        await service.track(CHAT_ID, "https://www.terabyteshop.com.br/produto/1")


async def test_track_rejects_duplicate(service: PriceService) -> None:
    await service.track(CHAT_ID, URL)

    with pytest.raises(PriceValidationError, match="já monitora"):
        await service.track(CHAT_ID, URL)


async def test_same_product_in_other_chat_is_allowed(service: PriceService) -> None:
    await service.track(CHAT_ID, URL)

    assert (await service.track(OTHER_CHAT_ID, URL)).chat_id == OTHER_CHAT_ID


async def test_track_respects_product_limit(service: PriceService, kabum: FakeSource) -> None:
    kabum.responses["https://www.kabum.com.br/produto/9"] = quote(10_00)
    for url in (URL, URL_2, URL_3):
        await service.track(CHAT_ID, url)

    with pytest.raises(PriceValidationError, match="Limite"):
        await service.track(CHAT_ID, "https://www.kabum.com.br/produto/9")


async def test_track_does_not_save_when_store_fails(
    service: PriceService, kabum: FakeSource
) -> None:
    kabum.responses[URL] = PriceFetchError("Preço não encontrado na página.")

    with pytest.raises(PriceFetchError):
        await service.track(CHAT_ID, URL)
    assert await service.list_products(CHAT_ID) == []


async def test_track_already_below_target_does_not_alert_again(
    service: PriceService, clock: FakeClock, notifier: FakeNotifier
) -> None:
    product = await service.track(CHAT_ID, URL, target_cents=120_00)
    assert product.target_alerted is True

    after_interval(clock)
    await service.check_due(notifier)

    assert notifier.sent == []


async def test_track_rejects_non_positive_target(service: PriceService) -> None:
    with pytest.raises(PriceValidationError):
        await service.track(CHAT_ID, URL, target_cents=0)


# ---- untrack ---------------------------------------------------------------


async def test_untrack_removes_product_and_history(
    service: PriceService, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    product = await service.track(CHAT_ID, URL)

    await service.untrack(CHAT_ID, product.id)

    assert await service.list_products(CHAT_ID) == []
    assert await count_points(session_factory) == 0


async def test_untrack_from_other_chat_raises(service: PriceService) -> None:
    product = await service.track(CHAT_ID, URL)

    with pytest.raises(ProductNotFoundError):
        await service.untrack(OTHER_CHAT_ID, product.id)


# ---- check_due -------------------------------------------------------------


async def test_check_due_ignores_products_not_yet_due(
    service: PriceService, kabum: FakeSource, notifier: FakeNotifier
) -> None:
    await service.track(CHAT_ID, URL)
    kabum.calls.clear()

    assert await service.check_due(notifier) == 0
    assert kabum.calls == []


async def test_check_due_updates_price_history_and_alerts_on_drop(
    service: PriceService,
    kabum: FakeSource,
    clock: FakeClock,
    notifier: FakeNotifier,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await service.track(CHAT_ID, URL)
    kabum.responses[URL] = quote(90_00)

    after_interval(clock)
    checked = await service.check_due(notifier)

    assert checked == 1
    [alert] = notifier.sent
    assert alert.kinds == (AlertKind.PRICE_DROP,)
    assert (alert.previous_cents, alert.product.last_price_cents) == (100_00, 90_00)
    assert alert.product.lowest_price_cents == 90_00
    assert alert.product.next_check_at > clock.now
    assert await count_points(session_factory) == 2


async def test_target_alert_is_sent_once(
    service: PriceService, kabum: FakeSource, clock: FakeClock, notifier: FakeNotifier
) -> None:
    await service.track(CHAT_ID, URL, target_cents=95_00)
    kabum.responses[URL] = quote(94_00)

    after_interval(clock)
    await service.check_due(notifier)
    after_interval(clock)
    await service.check_due(notifier)

    assert [a.kinds for a in notifier.sent] == [(AlertKind.TARGET_REACHED,)]


async def test_waits_between_requests(
    service: PriceService, clock: FakeClock, sleep: FakeSleep, notifier: FakeNotifier
) -> None:
    for url in (URL, URL_2, URL_3):
        await service.track(CHAT_ID, url)

    after_interval(clock)
    await service.check_due(notifier)

    assert len(sleep.calls) == 2  # entre a 1ª e a 2ª, e entre a 2ª e a 3ª
    assert all(3 <= seconds <= 8 for seconds in sleep.calls)


async def test_blocked_store_is_paused_but_other_stores_continue(
    service: PriceService,
    kabum: FakeSource,
    loja2: FakeSource,
    clock: FakeClock,
    notifier: FakeNotifier,
) -> None:
    for url in (URL, URL_2, URL_3):
        await service.track(CHAT_ID, url)
    kabum.responses[URL] = StoreBlockedError("HTTP 403")
    kabum.responses[URL_2] = StoreBlockedError("HTTP 403")
    kabum.calls.clear()
    loja2.calls.clear()

    after_interval(clock)
    await service.check_due(notifier)

    assert len(kabum.calls) == 1  # a 2ª da Kabum nem foi tentada
    assert loja2.calls == [URL_3]
    for product in await service.list_products(CHAT_ID):
        if product.store == "Kabum":
            assert product.next_check_at >= clock.now + STORE_PAUSE


async def test_alerts_after_three_blocks_in_a_row(
    service: PriceService, kabum: FakeSource, clock: FakeClock, notifier: FakeNotifier
) -> None:
    await service.track(CHAT_ID, URL)
    kabum.responses[URL] = StoreBlockedError("HTTP 403")

    for _ in range(4):
        clock.advance(STORE_PAUSE + CHECK_INTERVAL + CHECK_JITTER)
        await service.check_due(notifier)

    assert [a.kinds for a in notifier.sent] == [(AlertKind.STORE_BLOCKED,)]


async def test_alerts_once_after_three_read_failures(
    service: PriceService, kabum: FakeSource, clock: FakeClock, notifier: FakeNotifier
) -> None:
    await service.track(CHAT_ID, URL)
    kabum.responses[URL] = PriceFetchError("Preço não encontrado na página.")

    for _ in range(4):
        after_interval(clock)
        await service.check_due(notifier)

    assert [a.kinds for a in notifier.sent] == [(AlertKind.READ_FAILING,)]


async def test_success_resets_failures(
    service: PriceService, kabum: FakeSource, clock: FakeClock, notifier: FakeNotifier
) -> None:
    await service.track(CHAT_ID, URL)
    kabum.responses[URL] = PriceFetchError("falhou")
    after_interval(clock)
    await service.check_due(notifier)

    kabum.responses[URL] = quote(100_00)
    after_interval(clock)
    await service.check_due(notifier)

    [product] = await service.list_products(CHAT_ID)
    assert product.consecutive_failures == 0


async def test_notifier_failure_does_not_stop_the_batch(
    service: PriceService,
    kabum: FakeSource,
    clock: FakeClock,
    notifier: FakeNotifier,
) -> None:
    await service.track(CHAT_ID, URL)
    await service.track(CHAT_ID, URL_2)
    kabum.responses[URL] = quote(80_00)
    kabum.responses[URL_2] = quote(40_00)
    notifier.fail = True

    after_interval(clock)
    assert await service.check_due(notifier) == 2
