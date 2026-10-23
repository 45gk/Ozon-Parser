from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi.templating import Jinja2Templates

from app.core.config import settings

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

STATUS_LABELS = {
    "queued": "В очереди",
    "running": "Выполняется",
    "success": "Успех",
    "failed": "Ошибка",
}
SOURCE_LABELS = {
    "cdp": "Chrome CDP",
    "browser": "Playwright",
    "api": "Direct API",
    "html": "HTML",
}
CURRENCY_SYMBOLS = {
    "RUB": "₽",
    "KZT": "₸",
    "BYN": "Br",
    "UZS": "сум",
    "USD": "$",
    "EUR": "€",
}


def _timezone() -> ZoneInfo:
    try:
        return ZoneInfo(settings.display_timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(_timezone()).strftime("%d.%m.%Y %H:%M")


def format_duration(value: int | None) -> str:
    if value is None:
        return "—"
    if value < 1000:
        return f"{value} мс"
    seconds = value / 1000
    if seconds < 60:
        return f"{seconds:.1f} с"
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes} мин {rest} с"


def format_money(value, currency: str | None) -> str:
    if value in (None, ""):
        return "—"
    symbol = CURRENCY_SYMBOLS.get(currency or "", currency or "")
    return f"{value} {symbol}".strip()


def _pretty_number(value) -> str:
    if value in (None, ""):
        return "—"
    text = format(value, "f") if isinstance(value, Decimal) else str(value)
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        return text
    if number == number.to_integral_value():
        return f"{int(number):,}".replace(",", " ")
    return f"{number:,.2f}".replace(",", " ").replace(".", ",")


def format_money_pretty(value, currency: str | None) -> str:
    if value in (None, ""):
        return "—"
    symbol = CURRENCY_SYMBOLS.get(currency or "", currency or "")
    return f"{_pretty_number(value)} {symbol}".strip()


def format_rating(value) -> str:
    return f"{value} ★" if value not in (None, "") else "—"


def format_rating_pretty(value) -> str:
    if value in (None, ""):
        return "—"
    text = format(value, "f") if isinstance(value, Decimal) else str(value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{text} ★"


templates.env.filters["dt"] = format_datetime
templates.env.filters["duration"] = format_duration
templates.env.filters["money"] = format_money
templates.env.filters["money_pretty"] = format_money_pretty
templates.env.filters["rating"] = format_rating
templates.env.filters["rating_pretty"] = format_rating_pretty
templates.env.globals["status_labels"] = STATUS_LABELS
templates.env.globals["source_labels"] = SOURCE_LABELS
templates.env.globals["currency_symbols"] = CURRENCY_SYMBOLS
