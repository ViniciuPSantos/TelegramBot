import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

MAX_DAYS_BEFORE = 60

_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{4}))?$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_DAYS_BEFORE_RE = re.compile(r"--antes(?:\s+(\S+))?")


class ReminderParseError(ValueError):
    """Entrada inválida no /lembrete. A mensagem é mostrada ao usuário."""


@dataclass(frozen=True, slots=True)
class ParsedReminder:
    due_at: datetime
    text: str
    days_before: int | None = None


def parse_reminder(raw: str, *, now: datetime, default_hour: int = 9) -> ParsedReminder:
    """Interpreta '<data> [hora] <texto> [--antes N]'.

    `now` precisa ter timezone; a data retornada fica no mesmo fuso.
    """
    if now.tzinfo is None:
        raise ValueError("now precisa ter timezone")

    raw, days_before = _extract_days_before(raw)
    tokens = raw.split()
    if not tokens:
        raise ReminderParseError("Informe a data e o texto do lembrete.")

    day = _parse_date(tokens[0], today=now.date())
    tokens = tokens[1:]

    at = time(default_hour, 0)
    if tokens and (parsed_time := _parse_time(tokens[0])) is not None:
        at = parsed_time
        tokens = tokens[1:]

    text = " ".join(tokens)
    if not text:
        raise ReminderParseError("Faltou o texto do lembrete.")

    due_at = datetime.combine(day, at, tzinfo=now.tzinfo)
    if due_at <= now:
        raise ReminderParseError("Essa data/hora já passou.")

    return ParsedReminder(due_at=due_at, text=text, days_before=days_before)


def _extract_days_before(raw: str) -> tuple[str, int | None]:
    match = _DAYS_BEFORE_RE.search(raw)
    if match is None:
        return raw, None

    value = match.group(1)
    if value is None or not value.isdigit() or not 1 <= int(value) <= MAX_DAYS_BEFORE:
        raise ReminderParseError(
            f"Use --antes com um número de dias entre 1 e {MAX_DAYS_BEFORE}."
        )

    return raw[: match.start()] + raw[match.end() :], int(value)


def _parse_date(token: str, *, today: date) -> date:
    word = token.lower()
    if word == "hoje":
        return today
    if word in ("amanha", "amanhã"):
        return today + timedelta(days=1)

    match = _DATE_RE.match(token)
    if match is None:
        raise ReminderParseError(f"Não entendi a data '{token}'.")

    day, month, year = match.groups()
    try:
        if year is not None:
            return date(int(year), int(month), int(day))

        candidate = date(today.year, int(month), int(day))
        if candidate < today:
            candidate = candidate.replace(year=today.year + 1)
        return candidate
    except ValueError as exc:
        raise ReminderParseError(f"Data inválida: '{token}'.") from exc


def _parse_time(token: str) -> time | None:
    """Retorna None se o token não tem formato de hora (então ele faz parte do texto)."""
    match = _TIME_RE.match(token)
    if match is None:
        return None

    hour, minute = map(int, match.groups())
    try:
        return time(hour, minute)
    except ValueError as exc:
        raise ReminderParseError(f"Horário inválido: '{token}'.") from exc
