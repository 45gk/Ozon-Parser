import argparse
import json
import logging
import os
import sys
from pathlib import Path

from ozon_parser.api import fetch_product_api, parse_product_json
from ozon_parser.browser import fetch_product_browser
from ozon_parser.fetch import OzonFetchError, fetch_product
from ozon_parser.parser import OzonProductParseError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Извлечь данные из публичной карточки Ozon",
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="Полная ссылка на карточку товара на Ozon",
    )
    parser.add_argument(
        "--json",
        dest="json_file",
        metavar="FILE",
        help="Разобрать сохранённый ответ entrypoint-api (JSON-файл или '-' для stdin)",
    )
    parser.add_argument(
        "--source",
        choices=("api", "html", "browser"),
        default="api",
        help="Источник данных при загрузке из сети (по умолчанию: api)",
    )
    parser.add_argument(
        "--cookie",
        default=os.environ.get("OZON_COOKIE"),
        help="Cookie браузера для запроса к API (по умолчанию: переменная OZON_COOKIE)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Таймаут HTTP-запроса/загрузки страницы в секундах (по умолчанию: 30)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Запустить браузер без окна (Ozon чаще показывает challenge)",
    )
    parser.add_argument(
        "--channel",
        help="Канал Playwright: chrome, msedge или chromium (по умолчанию: авто)",
    )
    parser.add_argument(
        "--user-data-dir",
        metavar="DIR",
        help="Профиль браузера, чтобы сохранить cookie и пройденную проверку",
    )
    parser.add_argument(
        "--cdp-url",
        metavar="URL",
        help=(
            "Подключиться к уже запущенному Chrome по CDP, например "
            "http://127.0.0.1:9222 (надёжнее автоматического запуска)"
        ),
    )
    parser.add_argument(
        "--challenge-timeout",
        type=float,
        default=120.0,
        help="Сколько секунд ждать прохождения проверки Ozon (по умолчанию: 120)",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cdp_url and args.source == "html":
        parser.error("--cdp-url несовместим с --source html")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        if args.json_file:
            if args.json_file == "-":
                raw = sys.stdin.read()
            else:
                raw = Path(args.json_file).expanduser().read_text(encoding="utf-8")
            product = parse_product_json(raw, source_url=args.url)
        else:
            if not args.url:
                parser.error("укажи ссылку на товар или передай --json FILE")
            source = "browser" if args.cdp_url else args.source
            if source == "html":
                product = fetch_product(args.url, timeout=args.timeout)
            elif source == "browser":
                product = fetch_product_browser(
                    args.url,
                    headless=args.headless,
                    timeout=args.timeout,
                    challenge_timeout=args.challenge_timeout,
                    channel=args.channel,
                    user_data_dir=args.user_data_dir,
                    cdp_url=args.cdp_url,
                    cookie=args.cookie,
                )
            else:
                product = fetch_product_api(
                    args.url,
                    timeout=args.timeout,
                    cookie=args.cookie,
                )
    except (OSError, OzonFetchError, OzonProductParseError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(json.dumps(product.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
