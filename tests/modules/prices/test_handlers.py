import pytest

from assistant.modules.prices.handlers import parse_track_args
from assistant.modules.prices.money import MoneyParseError

URL = "https://www.kabum.com.br/produto/1/ssd"


def test_link_without_target() -> None:
    assert parse_track_args([URL]) == (URL, None)


def test_link_with_target() -> None:
    assert parse_track_args([URL, "1.149,90"]) == (URL, 114990)


def test_target_with_currency_symbol_split_by_space() -> None:
    # "/monitorar <link> R$ 1.149,90" chega como dois argumentos: "R$" e "1.149,90".
    assert parse_track_args([URL, "R$", "1.149,90"]) == (URL, 114990)


def test_invalid_target() -> None:
    with pytest.raises(MoneyParseError):
        parse_track_args([URL, "barato"])


def test_missing_link() -> None:
    with pytest.raises(MoneyParseError):
        parse_track_args([])
