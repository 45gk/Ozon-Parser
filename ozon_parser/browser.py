from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from ozon_parser.api import build_api_url, parse_product_json
from ozon_parser.fetch import OzonFetchError
from ozon_parser.parser import OzonProduct

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - depends on an optional extra
    PlaywrightError = Exception  # type: ignore[assignment,misc]
    PlaywrightTimeoutError = TimeoutError  # type: ignore[assignment,misc]
    sync_playwright = None

LOGGER = logging.getLogger(__name__)
_CHALLENGE_MARKERS = ("challenge.html", "captcha.html")


def _require_playwright() -> None:
    if sync_playwright is None:
        raise OzonFetchError(
            "Режим browser требует Playwright. Для локального запуска выполни "
            "`uv sync --extra browser`; дальше подойдёт установленный Chrome/Edge, "
            "а если их нет — `uv run playwright install chromium`. "
            "В Docker-образе браузерный режим не включён: запусти приложение "
            "локально, оставив PostgreSQL в Docker."
        )


def _connect_cdp(playwright: Any, cdp_url: str) -> Any:
    try:
        return playwright.chromium.connect_over_cdp(cdp_url)
    except PlaywrightError as first_error:
        # Playwright cannot attach to a browser with zero tabs; create one and retry.
        if cdp_url.startswith(("http://", "https://")):
            try:
                httpx.put(f"{cdp_url.rstrip('/')}/json/new?about:blank", timeout=5.0)
            except httpx.HTTPError:
                pass
            try:
                return playwright.chromium.connect_over_cdp(cdp_url)
            except PlaywrightError:
                pass
        raise first_error


def _open_context(
    playwright: Any,
    *,
    headless: bool,
    channel: str | None,
    user_data_dir: str | None,
    timeout: float,
) -> tuple[Any | None, Any]:
    """Launch Chrome/Edge/Chromium and return (browser, context)."""
    channels: list[str | None] = [channel] if channel else ["chrome", "msedge", None]
    errors: list[str] = []
    for candidate in channels:
        launch_args: dict[str, Any] = {
            "headless": headless,
            "timeout": timeout * 1000,
        }
        if candidate:
            launch_args["channel"] = candidate
        context_args: dict[str, Any] = {
            "locale": "ru-RU",
            "timezone_id": "Europe/Moscow",
            "viewport": {"width": 1366, "height": 900},
        }
        try:
            if user_data_dir:
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir,
                    **context_args,
                    **launch_args,
                )
                return None, context
            browser = playwright.chromium.launch(**launch_args)
            context = browser.new_context(**context_args)
            return browser, context
        except PlaywrightError as exc:
            errors.append(f"{candidate or 'bundled Chromium'}: {exc}")

    details = "\n".join(f"- {error}" for error in errors)
    raise OzonFetchError(
        "Не удалось запустить браузер. Установи Google Chrome, Microsoft Edge "
        "или выполни `uv run playwright install chromium`.\n"
        f"{details}"
    )


def _add_cookie_header(context: Any, cookie: str, product_url: str) -> None:
    host = urlparse(product_url).hostname
    if not cookie or not host:
        return
    cookies = []
    for part in cookie.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": host,
                "path": "/",
                "secure": True,
            }
        )
    if cookies:
        context.add_cookies(cookies)


def _is_challenge_url(url: str) -> bool:
    normalized = url.lower()
    return any(marker in normalized for marker in _CHALLENGE_MARKERS)


def _safe_title(page: Any) -> str:
    try:
        return page.title().strip()
    except PlaywrightError:
        return ""


def _page_challenge(page: Any) -> bool:
    try:
        if _is_challenge_url(page.url):
            return True
    except PlaywrightError:
        return False
    title = _safe_title(page).lower()
    return any(
        marker in title
        for marker in ("antibot", "challenge", "нет соединения", "доступ ограничен")
    )


def _wait_for_no_challenge(page: Any, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if not _page_challenge(page):
                page.wait_for_timeout(700)
                return True
            page.wait_for_timeout(1000)
        except PlaywrightError:
            return False
    return False


def _blocked_message(page: Any) -> str:
    title = _safe_title(page)
    if "нет соединения" in title.lower():
        return (
            "Ozon показал страницу «Похоже, нет соединения» — это антибот-блок "
            "для автоматизированного браузера, а не проблема сети. "
            "Обычный Chrome с твоим профилем может открыть карточку; надёжный "
            "путь — сохранить ответ entrypoint-api и передать его через --json."
        )
    return (
        "Ozon не пустил автоматизированный браузер к API. "
        "Попробуй --user-data-dir с профилем, где проверка уже пройдена, "
        "или сохрани ответ entrypoint-api и используй --json."
    )


def _handle_challenge(
    page: Any,
    product_url: str,
    *,
    challenge_url: str | None,
    headless: bool,
    timeout: float,
) -> None:
    if headless:
        raise OzonFetchError(
            "Ozon показал антибот-проверку в headless-браузере. "
            "Запусти без --headless и пройди проверку в открытом окне."
        )
    LOGGER.info(
        "Ozon показал проверку. Пройди её в открытом окне браузера (жду до %s сек).",
        int(timeout),
    )
    target = challenge_url or page.url
    try:
        page.goto(target, wait_until="domcontentloaded", timeout=timeout * 1000)
    except PlaywrightTimeoutError:
        pass
    if not _wait_for_no_challenge(page, timeout):
        raise OzonFetchError(_blocked_message(page))
    page.goto(product_url, wait_until="domcontentloaded", timeout=timeout * 1000)


def _fetch_api_in_page(page: Any, api_url: str) -> tuple[int, str]:
    script = """
    async (url) => {
      const response = await fetch(url, {
        credentials: 'include',
        headers: {accept: 'application/json, text/plain, */*'},
      });
      return {status: response.status, text: await response.text()};
    }
    """
    try:
        result = page.evaluate(script, api_url)
        if isinstance(result, dict):
            return int(result.get("status", 0)), str(result.get("text", ""))
    except PlaywrightError:
        pass

    # Fallback for pages whose CSP blocks fetch(): Playwright's request context
    # shares cookies with the opened browser.
    try:
        response = page.context.request.get(
            api_url,
            headers={
                "accept": "application/json, text/plain, */*",
                "referer": page.url,
            },
        )
        return response.status, response.text()
    except PlaywrightError as exc:
        raise OzonFetchError(
            f"Не удалось запросить API из открытого браузера: {exc}"
        ) from exc


def _payload(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _challenge_url(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    for key in ("challengeURL", "challengeUrl", "captchaURL", "captchaUrl"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def fetch_product_browser(
    product_url: str,
    *,
    headless: bool = False,
    timeout: float = 60.0,
    challenge_timeout: float = 120.0,
    channel: str | None = None,
    user_data_dir: str | None = None,
    cdp_url: str | None = None,
    cookie: str | None = None,
) -> OzonProduct:
    """Fetch a product via a real browser executing the API request in-page.

    Without ``cdp_url`` Playwright launches its own Chrome/Edge/Chromium. With
    ``cdp_url`` it connects to a Chrome the user started with
    ``--remote-debugging-port``; that browser is not marked as automated and is
    much more likely to pass Ozon's check.
    """
    api_url = build_api_url(product_url)
    _require_playwright()

    with sync_playwright() as playwright:
        page = None
        context = None
        browser = None
        owned_context = False
        owned_browser = False
        if cdp_url:
            try:
                browser = _connect_cdp(playwright, cdp_url)
            except PlaywrightError as exc:
                raise OzonFetchError(
                    "Не удалось подключиться к Chrome по CDP. Запусти Chrome так:\n"
                    '"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" '
                    "--remote-debugging-port=9222 "
                    '--user-data-dir="$HOME/.ozon-chrome"\n'
                    "потом повтори с --cdp-url http://127.0.0.1:9222."
                ) from exc
            if browser.contexts:
                context = browser.contexts[0]
            else:
                context = browser.new_context(
                    locale="ru-RU", timezone_id="Europe/Moscow"
                )
                owned_context = True
            page = context.new_page()
        else:
            browser, context = _open_context(
                playwright,
                headless=headless,
                channel=channel,
                user_data_dir=user_data_dir,
                timeout=timeout,
            )
            owned_context = True
            owned_browser = browser is not None
            page = context.pages[0] if context.pages else context.new_page()

        try:
            _add_cookie_header(context, cookie or "", product_url)
            page.set_default_timeout(timeout * 1000)
            if cdp_url:
                try:
                    page.bring_to_front()
                except PlaywrightError:
                    pass

            try:
                page.goto(
                    product_url,
                    wait_until="domcontentloaded",
                    timeout=timeout * 1000,
                )
            except PlaywrightTimeoutError:
                pass

            status, text = _fetch_api_in_page(page, api_url)
            if status == 200:
                return parse_product_json(text, source_url=product_url)

            data = _payload(text)
            if status in {403, 429} or (data and data.get("incidentId")):
                challenge = _challenge_url(data)
                if challenge:
                    _handle_challenge(
                        page,
                        product_url,
                        challenge_url=challenge,
                        headless=headless,
                        timeout=challenge_timeout,
                    )
                    status, text = _fetch_api_in_page(page, api_url)
                    if status == 200:
                        return parse_product_json(text, source_url=product_url)
                if headless and not cdp_url:
                    raise OzonFetchError(
                        "Ozon отклонил запрос из headless-браузера. "
                        "Запусти без --headless, чтобы пройти проверку вручную."
                    )
                raise OzonFetchError(_blocked_message(page))

            raise OzonFetchError(f"Ozon API вернул HTTP {status} из браузера.")
        finally:
            if cdp_url and page is not None:
                try:
                    page.close()
                except PlaywrightError:
                    pass
            if owned_context and context is not None:
                try:
                    context.close()
                finally:
                    if owned_browser and browser is not None:
                        browser.close()
