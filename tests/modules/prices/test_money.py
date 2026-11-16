import pytest

from assistant.modules.prices.money import MoneyParseError, drop_percent, format_brl, parse_brl


@pytest.mark.parametrize(
    ("cents", "expected"),
    [
        (0, "R$ 0,00"),
        (5, "R$ 0,05"),
        (114990, "R$ 1.149,90"),
        (123456789, "R$ 1.234.567,89"),
        (-1050, "-R$ 10,50"),
    ],
)
def test_format_brl(cents: int, expected: str) -> None:
    assert format_brl(cents) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.149,90", 114990),
        ("1149,90", 114990),
        ("1149.90", 114990),
        ("1149.9", 114990),
        ("1149", 114900),
        ("1.149", 114900),  # ponto com 3 dígitos depois é milhar
        ("1.234.567,8", 123456780),
        ("R$ 1.149,90", 114990),
        ("R$1149", 114900),
        ("  99,9  ", 9990),
        ("0,01", 1),
    ],
)
def test_parse_brl_accepts_common_formats(text: str, expected: int) -> None:
    assert parse_brl(text) == expected


@pytest.mark.parametrize(
    "text", ["", "abc", "1,149.90", "1.14.9", "12,345", "-10", "1e3", "1.1490", "10,"]
)
def test_parse_brl_rejects_invalid_values(text: str) -> None:
    with pytest.raises(MoneyParseError):
        parse_brl(text)


@pytest.mark.parametrize("text", ["0", "0,00", "200000000"])
def test_parse_brl_rejects_zero_and_absurd_values(text: str) -> None:
    with pytest.raises(MoneyParseError):
        parse_brl(text)


def test_drop_percent() -> None:
    assert drop_percent(10000, 9450) == 5
    assert drop_percent(10000, 10000) == 0
    assert drop_percent(10000, 11000) == 0
