import pytest

from assistant.modules.prices.rules import (
    AlertKind,
    Evaluation,
    PriceState,
    evaluate,
    is_relevant_drop,
)
from assistant.modules.prices.sources import PriceQuote


def state(
    last: int = 100_00,
    *,
    in_stock: bool = True,
    target: int | None = None,
    alerted: bool = False,
) -> PriceState:
    return PriceState(
        last_price_cents=last, in_stock=in_stock, target_cents=target, target_alerted=alerted
    )


def quote(price: int, *, in_stock: bool = True) -> PriceQuote:
    return PriceQuote(title="SSD", price_cents=price, in_stock=in_stock)


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (100_00, 99_00, True),  # exatamente 1%
        (100_00, 99_01, False),  # 0,99%: ruído
        (100_00, 100_00, False),
        (100_00, 120_00, False),  # subiu
    ],
)
def test_is_relevant_drop(old: int, new: int, expected: bool) -> None:
    assert is_relevant_drop(old, new) is expected


def test_without_target_alerts_on_relevant_drop() -> None:
    assert evaluate(state(100_00), quote(90_00)) == Evaluation((AlertKind.PRICE_DROP,), False)


def test_without_target_ignores_small_drop() -> None:
    assert evaluate(state(100_00), quote(99_50)).alerts == ()


def test_target_reached_alerts_once() -> None:
    first = evaluate(state(100_00, target=90_00), quote(89_90))
    again = evaluate(state(89_90, target=90_00, alerted=first.target_alerted), quote(85_00))

    assert first == Evaluation((AlertKind.TARGET_REACHED,), True)
    assert again == Evaluation((), True)


def test_target_rearms_when_price_goes_back_up() -> None:
    result = evaluate(state(89_00, target=90_00, alerted=True), quote(95_00))

    assert result == Evaluation((), False)


def test_with_target_ignores_drops_above_target() -> None:
    assert evaluate(state(150_00, target=90_00), quote(120_00)).alerts == ()


def test_out_of_stock_does_not_trigger_target() -> None:
    result = evaluate(state(100_00, target=90_00), quote(80_00, in_stock=False))

    assert result == Evaluation((), False)


def test_back_in_stock_below_target_sends_both_alerts() -> None:
    result = evaluate(state(80_00, in_stock=False, target=90_00), quote(80_00))

    assert result.alerts == (AlertKind.BACK_IN_STOCK, AlertKind.TARGET_REACHED)


def test_back_in_stock_without_price_change() -> None:
    assert evaluate(state(100_00, in_stock=False), quote(100_00)).alerts == (
        AlertKind.BACK_IN_STOCK,
    )
