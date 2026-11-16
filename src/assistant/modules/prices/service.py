"""Regras de negócio do monitor de preços."""

import asyncio
import logging
import random
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from urllib.parse import urlsplit

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from assistant.core.clock import Clock, utc_now
from assistant.modules.prices.models import (
    TITLE_MAX_LENGTH,
    URL_MAX_LENGTH,
    PricePoint,
    TrackedProduct,
)
from assistant.modules.prices.repository import TrackedProductRepository
from assistant.modules.prices.rules import AlertKind, PriceState, evaluate
from assistant.modules.prices.sources import (
    PriceFetchError,
    PriceQuote,
    PriceSource,
    StoreBlockedError,
    UnsupportedStoreError,
    find_source,
)

logger = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]

MAX_PRODUCTS = 30
CHECK_INTERVAL = timedelta(hours=8)
CHECK_JITTER = timedelta(minutes=30)
STORE_PAUSE = timedelta(hours=6)
FAILURES_BEFORE_ALERT = 3
BATCH_SIZE = 10
PAUSE_BETWEEN_REQUESTS = (3.0, 8.0)  # segundos


class ProductNotFoundError(Exception):
    """O produto não existe (ou pertence a outro chat)."""


class PriceValidationError(ValueError):
    """Regra de negócio violada. A mensagem é mostrada ao usuário."""


@dataclass(frozen=True, slots=True)
class PriceAlert:
    product: TrackedProduct
    kinds: tuple[AlertKind, ...]
    previous_cents: int


class PriceNotifier(Protocol):
    async def notify(self, alert: PriceAlert) -> None: ...


def normalize_url(url: str) -> str:
    """Tira espaços e o fragmento (#...), que não muda a página."""
    return urlsplit(url.strip())._replace(fragment="").geturl()


class PriceService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sources: Sequence[PriceSource],
        *,
        clock: Clock = utc_now,
        sleep: Sleep = asyncio.sleep,
        rng: random.Random | None = None,
        max_products: int = MAX_PRODUCTS,
    ) -> None:
        self._session_factory = session_factory
        self._sources = list(sources)
        self._clock = clock
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._max_products = max_products
        # Estado do backoff por loja. Fica em memória: se o bot reiniciar, no pior caso
        # a loja recebe uma requisição a mais e o bot volta a pausá-la.
        self._paused_until: dict[str, datetime] = {}
        self._blocks: dict[str, int] = {}

    @asynccontextmanager
    async def _repository(self) -> AsyncIterator[TrackedProductRepository]:
        async with self._session_factory() as session, session.begin():
            yield TrackedProductRepository(session)

    # ---- comandos do usuário ----------------------------------------------

    async def track(
        self, chat_id: int, url: str, target_cents: int | None = None
    ) -> TrackedProduct:
        url = normalize_url(url)
        if len(url) > URL_MAX_LENGTH:
            raise PriceValidationError("Esse link é longo demais.")
        if target_cents is not None and target_cents <= 0:
            raise PriceValidationError("O preço-alvo precisa ser maior que zero.")
        source = find_source(self._sources, url)  # UnsupportedStoreError sobe para o handler

        async with self._repository() as repo:
            if await repo.find_by_url(chat_id, url) is not None:
                raise PriceValidationError("Você já monitora esse produto.")
            if await repo.count_by_chat(chat_id) >= self._max_products:
                raise PriceValidationError(
                    f"Limite de {self._max_products} produtos atingido. Remova algum em /produtos."
                )

        # A consulta à loja fica FORA da transação: rede lenta não deve segurar o banco.
        quote = await source.fetch(url)  # PriceFetchError também sobe para o handler

        now = self._clock()
        product = TrackedProduct(
            chat_id=chat_id,
            url=url,
            store=source.name,
            title=quote.title[:TITLE_MAX_LENGTH] or "Produto sem nome",
            target_cents=target_cents,
            # Se já começa abaixo do alvo, a resposta do comando mostra isso: não avisa de novo.
            target_alerted=_reached(target_cents, quote),
            last_price_cents=quote.price_cents,
            lowest_price_cents=quote.price_cents,
            in_stock=quote.in_stock,
            last_checked_at=now,
            next_check_at=self._next_check(now),
        )
        try:
            async with self._repository() as repo:
                await repo.add(product)
                await repo.add_point(_point(product.id, quote, now))
        except IntegrityError as exc:  # dois /monitorar do mesmo link ao mesmo tempo
            raise PriceValidationError("Você já monitora esse produto.") from exc

        logger.info("produto monitorado", extra={"product_id": product.id, "store": source.name})
        return product

    async def list_products(self, chat_id: int) -> Sequence[TrackedProduct]:
        async with self._repository() as repo:
            return await repo.list_by_chat(chat_id)

    async def untrack(self, chat_id: int, product_id: int) -> None:
        async with self._repository() as repo:
            product = await repo.get(product_id, chat_id=chat_id)
            if product is None:
                raise ProductNotFoundError(f"Produto {product_id} não encontrado.")
            await repo.delete(product)

    # ---- verificação periódica --------------------------------------------

    async def check_due(self, notifier: PriceNotifier) -> int:
        """Verifica os produtos vencidos e devolve quantos foram lidos com sucesso."""
        async with self._repository() as repo:
            due = await repo.list_due(self._clock(), limit=BATCH_SIZE)

        checked = 0
        fetched_any = False
        for product in due:
            try:
                source = find_source(self._sources, product.url)
            except UnsupportedStoreError:
                logger.warning("loja não é mais suportada", extra={"product_id": product.id})
                await self._reschedule(product, self._next_check(self._clock()))
                continue

            paused_until = self._paused_until.get(source.name)
            if paused_until is not None and paused_until > self._clock():
                # Empurra para depois da pausa, para não ocupar o lote das outras lojas.
                await self._reschedule(product, paused_until + self._jitter(positive_only=True))
                continue

            if fetched_any:  # pausa entre requisições, como uma pessoa navegando
                await self._sleep(self._rng.uniform(*PAUSE_BETWEEN_REQUESTS))
            fetched_any = True

            alert: PriceAlert | None
            try:
                quote = await source.fetch(product.url)
            except StoreBlockedError:
                alert = await self._on_blocked(product, source.name)
            except PriceFetchError as exc:
                alert = await self._on_failure(product, exc)
            else:
                alert = await self._on_quote(product, source.name, quote)
                checked += 1

            if alert is not None:
                await self._send(notifier, alert)
        return checked

    async def _on_quote(
        self, product: TrackedProduct, store: str, quote: PriceQuote
    ) -> PriceAlert | None:
        self._blocks.pop(store, None)  # a loja respondeu: zera a contagem de bloqueios
        now = self._clock()
        async with self._repository() as repo:
            current = await repo.get(product.id, chat_id=product.chat_id)
            if current is None:
                return None  # removido durante a verificação
            previous = current.last_price_cents
            result = evaluate(
                PriceState(
                    last_price_cents=current.last_price_cents,
                    in_stock=current.in_stock,
                    target_cents=current.target_cents,
                    target_alerted=current.target_alerted,
                ),
                quote,
            )
            current.last_price_cents = quote.price_cents
            current.lowest_price_cents = min(current.lowest_price_cents, quote.price_cents)
            current.in_stock = quote.in_stock
            current.target_alerted = result.target_alerted
            current.consecutive_failures = 0
            current.last_checked_at = now
            current.next_check_at = self._next_check(now)
            await repo.add_point(_point(current.id, quote, now))

        if not result.alerts:
            return None
        return PriceAlert(current, result.alerts, previous)

    async def _on_blocked(self, product: TrackedProduct, store: str) -> PriceAlert | None:
        blocks = self._blocks.get(store, 0) + 1
        self._blocks[store] = blocks
        until = self._clock() + STORE_PAUSE
        self._paused_until[store] = until
        logger.warning("loja recusou a consulta", extra={"store": store, "blocks": blocks})

        await self._reschedule(product, until + self._jitter(positive_only=True))
        if blocks == FAILURES_BEFORE_ALERT:
            return PriceAlert(product, (AlertKind.STORE_BLOCKED,), product.last_price_cents)
        return None

    async def _on_failure(self, product: TrackedProduct, exc: PriceFetchError) -> PriceAlert | None:
        logger.warning("falha ao ler preço", extra={"product_id": product.id, "error": str(exc)})
        async with self._repository() as repo:
            current = await repo.get(product.id, chat_id=product.chat_id)
            if current is None:
                return None
            current.consecutive_failures += 1
            current.next_check_at = self._next_check(self._clock())

        if current.consecutive_failures == FAILURES_BEFORE_ALERT:
            return PriceAlert(current, (AlertKind.READ_FAILING,), current.last_price_cents)
        return None

    async def _reschedule(self, product: TrackedProduct, when: datetime) -> None:
        async with self._repository() as repo:
            current = await repo.get(product.id, chat_id=product.chat_id)
            if current is not None:
                current.next_check_at = when

    @staticmethod
    async def _send(notifier: PriceNotifier, alert: PriceAlert) -> None:
        # Aviso de preço é informativo: se o envio falhar, registra no log e segue com os outros.
        try:
            await notifier.notify(alert)
        except Exception:
            logger.exception(
                "falha ao enviar aviso de preço", extra={"product_id": alert.product.id}
            )

    def _next_check(self, now: datetime) -> datetime:
        return now + CHECK_INTERVAL + self._jitter()

    def _jitter(self, *, positive_only: bool = False) -> timedelta:
        limit = CHECK_JITTER.total_seconds()
        low = 0.0 if positive_only else -limit
        return timedelta(seconds=self._rng.uniform(low, limit))


def _reached(target_cents: int | None, quote: PriceQuote) -> bool:
    return target_cents is not None and quote.in_stock and quote.price_cents <= target_cents


def _point(product_id: int, quote: PriceQuote, checked_at: datetime) -> PricePoint:
    return PricePoint(
        product_id=product_id,
        price_cents=quote.price_cents,
        in_stock=quote.in_stock,
        checked_at=checked_at,
    )
