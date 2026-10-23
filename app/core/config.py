from __future__ import annotations

import os
from dataclasses import dataclass


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_name: str = "Ozon Parse Lab"
    app_version: str = "0.4.0"
    database_url: str = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://ozon:ozon-dev@localhost:5432/ozon",
    )
    cdp_url: str = os.environ.get("CDP_URL", "http://127.0.0.1:9222")
    ozon_cookie: str | None = os.environ.get("OZON_COOKIE") or None
    default_timeout: float = _float_env("PARSE_TIMEOUT", 45.0)
    default_challenge_timeout: float = _float_env("CHALLENGE_TIMEOUT", 120.0)
    page_size: int = _int_env("PAGE_SIZE", 20)
    display_timezone: str = os.environ.get("DISPLAY_TIMEZONE", "Europe/Moscow")


settings = Settings()
