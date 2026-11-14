from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from assistant.modules.reminders.parser import (
    ParsedReminder,
    ReminderParseError,
    parse_reminder,
)

TZ = ZoneInfo("America/Sao_Paulo")
NOW = datetime(2026, 11, 12, 10, 0, tzinfo=TZ)


def dt(*args: int) -> datetime:
    return datetime(*args, tzinfo=TZ)


def parse(raw: str) -> ParsedReminder:
    return parse_reminder(raw, now=NOW, default_hour=9)


@pytest.mark.parametrize(
    ("raw", "expected_due", "expected_text"),
    [
        ("15/11 pagar fatura", dt(2026, 11, 15, 9, 0), "pagar fatura"),
        ("15/11 14:30 reunião", dt(2026, 11, 15, 14, 30), "reunião"),
        ("amanha 10:00 dentista", dt(2026, 11, 13, 10, 0), "dentista"),
        ("amanhã 10:00 dentista", dt(2026, 11, 13, 10, 0), "dentista"),
        ("hoje 18:00 academia", dt(2026, 11, 12, 18, 0), "academia"),
        ("HOJE 18:00 academia", dt(2026, 11, 12, 18, 0), "academia"),
        ("12/11 18:00 ainda hoje", dt(2026, 11, 12, 18, 0), "ainda hoje"),
        ("10/11 aniversário", dt(2027, 11, 10, 9, 0), "aniversário"),
        ("05/01/2027 9:05 consulta", dt(2027, 1, 5, 9, 5), "consulta"),
        ("20/11 2 pacotes", dt(2026, 11, 20, 9, 0), "2 pacotes"),
    ],
)
def test_parse_valid_input(raw: str, expected_due: datetime, expected_text: str) -> None:
    result = parse(raw)

    assert result.due_at == expected_due
    assert result.text == expected_text
    assert result.days_before is None


@pytest.mark.parametrize(
    "raw",
    [
        "15/11 pagar fatura --antes 3",
        "15/11 --antes 3 pagar fatura",
        "--antes 3 15/11 pagar fatura",
        # O Telegram troca "--" por travessão automaticamente.
        "15/11 pagar fatura —antes 3",
        "15/11 pagar fatura –antes 3",
    ],
)
def test_extracts_days_before_from_any_position(raw: str) -> None:
    result = parse(raw)

    assert result.days_before == 3
    assert result.text == "pagar fatura"
    assert result.due_at == dt(2026, 11, 15, 9, 0)


@pytest.mark.parametrize(
    ("raw", "error_fragment"),
    [
        ("", "Informe a data"),
        ("pagar fatura", "Não entendi a data"),
        ("15/11", "Faltou o texto"),
        ("15/11 14:30", "Faltou o texto"),
        ("31/02 x", "Data inválida"),
        ("15/13 x", "Data inválida"),
        ("15/11 25:00 x", "Horário inválido"),
        ("15/11 14:60 x", "Horário inválido"),
        ("hoje 08:00 x", "já passou"),
        ("hoje x", "já passou"),  # sem hora = 09:00, mas já são 10:00
        ("12/11 09:59 x", "já passou"),  # hoje com hora passada: erro, não ano que vem
        ("01/01/2020 x", "já passou"),
        ("15/11 x --antes", "--antes"),
        ("15/11 x --antes abc", "--antes"),
        ("15/11 x --antes 0", "--antes"),
        ("15/11 x --antes 61", "--antes"),
    ],
)
def test_rejects_invalid_input(raw: str, error_fragment: str) -> None:
    with pytest.raises(ReminderParseError, match=error_fragment):
        parse(raw)


def test_requires_timezone_aware_now() -> None:
    with pytest.raises(ValueError, match="timezone"):
        parse_reminder("amanha x", now=datetime(2026, 11, 12, 10, 0))
