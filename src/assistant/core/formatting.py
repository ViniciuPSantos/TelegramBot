from datetime import datetime
from zoneinfo import ZoneInfo

_WEEKDAYS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


def format_datetime(value: datetime, tz: ZoneInfo) -> str:
    """Ex: 'seg 15/11/2026 09:00' no fuso do user"""
    local = value.astimezone(tz)
    return f"{_WEEKDAYS[local.weekday()]} {local:%d/%m/%Y %H:%M}"


def truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"
