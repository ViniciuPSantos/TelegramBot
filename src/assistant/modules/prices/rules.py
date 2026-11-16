from dataclasses import dataclass
from enum import StrEnum

from assistant.modules.prices.sources import PriceQuote

MIN_DROP_PERCENT = 1


class AlertKind(StrEnum):
    TARGET_REACHED = "target_reached"
    PRICE_DROP = "price_drop"
    BACK_IN_STOCK = "back_in_stock"
    READ_FAILING = "read_failing"
    STORE_BLOCKED = "store_blocked"


@dataclass(frozen=True, slots=True)
class PriceState:
    last_price_cents: int
    in_stock: bool
    target_cents: int | None
    target_alerted: bool


@dataclass(frozen=True, slots=True)
class Evaluation:
    alerts: tuple[AlertKind, ...]
    target_alerted: bool


def evaluate(state: PriceState, quote: PriceQuote) -> Evaluation:
    alerts: list[AlertKind] = []

    if quote.in_stock and not state.in_stock:
        alerts.append(AlertKind.BACK_IN_STOCK)

    target_alerted = state.target_alerted
    if state.target_cents is not None:
        if quote.price_cents > state.target_cents:
            target_alerted = False
        elif quote.in_stock and not target_alerted:
            alerts.append(AlertKind.TARGET_REACHED)
            target_alerted = True
    elif quote.in_stock and is_relevant_drop(state.last_price_cents, quote.price_cents):
        alerts.append(AlertKind.PRICE_DROP)

    return Evaluation(tuple(alerts), target_alerted)


def is_relevant_drop(old_cents: int, new_cents: int) -> bool:
    return new_cents < old_cents and (old_cents - new_cents) * 100 >= old_cents * MIN_DROP_PERCENT
