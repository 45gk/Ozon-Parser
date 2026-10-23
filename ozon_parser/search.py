from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from urllib.parse import urlencode, urljoin, urlparse, urlunparse

from ozon_parser.api import API_PATH, _decode_states, _state
from ozon_parser.browser import (
    PlaywrightError,
    PlaywrightTimeoutError,
    _add_cookie_header,
    _challenge_url,
    _connect_cdp,
    _fetch_api_in_page,
    _handle_challenge,
    _open_context,
    _page_challenge,
    _require_playwright,
    sync_playwright,
)
from ozon_parser.urls import is_ozon_host


class OzonSearchError(RuntimeError):
    """Raised when a search page cannot be fetched or parsed."""


class OzonSearchParseError(OzonSearchError):
    """Raised when a search response has no recognizable tile grid."""


@dataclass(frozen=True)
class OzonSearchItem:
    position: int
    sku: str | None
    product_url: str
    name: str | None
    price: Decimal | None
    original_price: Decimal | None
    currency: str | None
    discount: str | None
    rating: Decimal | None
    review_count: int | None
    image_url: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "sku": self.sku,
            "product_url": self.product_url,
            "name": self.name,
            "price": str(self.price) if self.price is not None else None,
            "original_price": (
                str(self.original_price) if self.original_price is not None else None
            ),
            "currency": self.currency,
            "discount": self.discount,
            "rating": str(self.rating) if self.rating is not None else None,
            "review_count": self.review_count,
            "image_url": self.image_url,
        }


@dataclass(frozen=True)
class OzonSearchResult:
    search_url: str | None
    query: str | None
    title: str | None
    items: tuple[OzonSearchItem, ...]
    next_page: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "search_url": self.search_url,
            "query": self.query,
            "title": self.title,
            "items": [item.to_dict() for item in self.items],
            "next_page": self.next_page,
        }


_SYMBOLS = (
    ("₽", "RUB"),
    ("₸", "KZT"),
    ("₴", "UAH"),
    ("₾", "GEL"),
    ("֏", "AMD"),
    ("$", "USD"),
    ("€", "EUR"),
)


def _load_json(payload: Any) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        return dict(payload)
    if isinstance(payload, (bytes, bytearray)):
        try:
            text = bytes(payload).decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise OzonSearchParseError(
                "Поисковый ответ Ozon не является UTF-8 JSON."
            ) from exc
    elif isinstance(payload, str):
        text = payload.lstrip("\ufeff")
    else:
        raise OzonSearchParseError(
            f"Ожидался JSON поисковой выдачи, получено: {type(payload).__name__}."
        )

    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[A-Za-z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    text = text.strip("`").strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OzonSearchParseError(
            f"Не удалось разобрать JSON поисковой выдачи: {exc}."
        ) from exc

    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise OzonSearchParseError(
                "Поисковый ответ содержит строку, а не объект."
            ) from exc
    if not isinstance(data, dict):
        raise OzonSearchParseError("Поисковый ответ Ozon должен быть JSON-объектом.")
    return data


def _text(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (str, int, float, Decimal)):
        text = str(value).strip()
        return text or None
    if isinstance(value, dict):
        for key in ("text", "content", "title", "name", "value"):
            text = _text(value.get(key))
            if text:
                return text
    return None


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    cleaned = re.sub(r"[^\d,.-]", "", str(value)).replace(",", ".")
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _integer(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    cleaned = re.sub(r"\D", "", str(value))
    return int(cleaned) if cleaned else None


def _currency(value: Any) -> str | None:
    text = _text(value) or ""
    for symbol, code in _SYMBOLS:
        if symbol in text:
            return code
    return None


def _normalise_product_url(link: str, base_url: str) -> str | None:
    absolute = urljoin(base_url, link)
    parsed = urlparse(absolute)
    if not is_ozon_host(parsed.hostname) or not parsed.path.startswith("/product/"):
        return None
    path = parsed.path.rstrip("/") + "/"
    return urlunparse(("https", parsed.hostname, path, "", "", ""))


def _rating_and_reviews(main_state: list[Any]) -> tuple[Decimal | None, int | None]:
    for block in main_state:
        if not isinstance(block, dict) or block.get("type") != "labelListV2":
            continue
        label_list = block.get("labelListV2")
        if not isinstance(label_list, dict):
            continue
        test_info = label_list.get("testInfo")
        automation = (
            test_info.get("automatizationId") if isinstance(test_info, dict) else None
        )
        items = label_list.get("items")
        if not isinstance(items, list):
            continue
        texts = []
        for item in items:
            if isinstance(item, dict) and item.get("type") == "text":
                text = _text(item.get("text"))
                if text:
                    texts.append(text)
        if automation != "tile-list-rating" and not any("★" in text for text in texts):
            # The rating block is recognizable by its star icon; fall back to
            # a textual rating only when there is no automation id at all.
            if not any(re.fullmatch(r"\d(?:[.,]\d)?", text) for text in texts):
                continue
        rating = next(
            (_decimal(text) for text in texts if re.fullmatch(r"\d(?:[.,]\d)?", text)),
            None,
        )
        review_count = next(
            (
                _integer(match.group(1))
                for text in texts
                if (match := re.search(r"(\d[\d\s\u00a0]*)\s*отзыв", text))
            ),
            None,
        )
        return rating, review_count
    return None, None


def _parse_item(item: Any, position: int, base_url: str) -> OzonSearchItem | None:
    if not isinstance(item, dict):
        return None
    action = item.get("action")
    link = action.get("link") if isinstance(action, dict) else None
    if not isinstance(link, str) or not link:
        return None
    product_url = _normalise_product_url(link, base_url)
    if not product_url:
        return None

    main_state = item.get("mainState")
    main_state = main_state if isinstance(main_state, list) else []

    name = None
    price = None
    price_text = None
    original_price = None
    discount = None
    for block in main_state:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "priceV2":
            price_v2 = block.get("priceV2")
            if not isinstance(price_v2, dict):
                continue
            prices = price_v2.get("price")
            if isinstance(prices, list):
                for price_item in prices:
                    if not isinstance(price_item, dict):
                        continue
                    if price_item.get("textStyle") == "PRICE":
                        price = _decimal(price_item.get("text"))
                        price_text = _text(price_item.get("text"))
                    elif price_item.get("textStyle") == "ORIGINAL_PRICE":
                        original_price = _decimal(price_item.get("text"))
            discount = _text(price_v2.get("discount"))
        elif block.get("type") == "textDS":
            text_ds = block.get("textDS")
            if not isinstance(text_ds, dict):
                continue
            test_info = text_ds.get("testInfo")
            is_name = block.get("id") == "name" or (
                isinstance(test_info, dict)
                and test_info.get("automatizationId") == "tile-name"
            )
            if is_name:
                name = _text(text_ds.get("text"))

    rating, review_count = _rating_and_reviews(main_state)

    image_url = None
    tile_image = item.get("tileImage")
    if isinstance(tile_image, dict):
        images = tile_image.get("items")
        if isinstance(images, list):
            for image_item in images:
                if not isinstance(image_item, dict):
                    continue
                image = image_item.get("image")
                if isinstance(image, dict):
                    image_url = _text(image.get("link"))
                    if image_url:
                        break
        if not image_url:
            image = tile_image.get("image")
            if isinstance(image, dict):
                image_url = _text(image.get("link"))

    sku = _text(item.get("sku") or item.get("id"))
    if not sku:
        match = re.search(r"-(\d+)/?$", product_url)
        sku = match.group(1) if match else None

    currency = _currency(price_text)

    return OzonSearchItem(
        position=position,
        sku=sku,
        product_url=product_url,
        name=name,
        price=price,
        original_price=original_price,
        currency=currency,
        discount=discount,
        rating=rating,
        review_count=review_count,
        image_url=image_url,
    )


def build_search_api_url(search_url: str) -> str:
    """Build the entrypoint-api URL for a category/search page."""
    parsed = urlparse(search_url)
    if parsed.scheme not in {"http", "https"} or not is_ozon_host(parsed.hostname):
        raise OzonSearchError("Укажи ссылку на выдачу Ozon.")
    if not (parsed.path.startswith("/category/") or parsed.path.startswith("/search/")):
        raise OzonSearchError(
            "Нужна ссылка на выдачу Ozon: /category/... или /search/..."
        )
    target = parsed.path
    if parsed.query:
        target = f"{target}?{parsed.query}"
    return f"https://{parsed.hostname}{API_PATH}?{urlencode({'url': target})}"


def parse_search_json(
    payload: Any,
    search_url: str | None = None,
) -> OzonSearchResult:
    data = _load_json(payload)
    incident = data.get("incidentId") or data.get("incident_id")
    if incident:
        raise OzonSearchParseError(
            "Ozon вернул антибот-заглушку вместо поисковой выдачи "
            f"(incidentId: {incident})."
        )

    raw_states = data.get("widgetStates")
    if not isinstance(raw_states, dict):
        raise OzonSearchParseError(
            "В JSON нет widgetStates — это не ответ Ozon entrypoint-api."
        )
    states = _decode_states(raw_states)
    grid = _state(states, "tileGridDesktop")
    if not grid:
        raise OzonSearchParseError(
            "В ответе нет виджета tileGridDesktop — это не поисковая выдача."
        )
    raw_items = grid.get("items")
    raw_items = raw_items if isinstance(raw_items, list) else []

    base_url = "https://www.ozon.ru"
    if search_url:
        parsed = urlparse(search_url)
        if parsed.scheme and parsed.netloc:
            base_url = f"{parsed.scheme}://{parsed.netloc}"

    items: list[OzonSearchItem] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        item = _parse_item(raw_item, len(items) + 1, base_url)
        if item is None:
            continue
        key = item.sku or item.product_url
        if key in seen:
            continue
        seen.add(key)
        items.append(item)

    search_bar = _state(states, "searchBarDesktop")
    query = _text(search_bar.get("text"))
    seo = data.get("seo")
    title = _text(seo.get("title")) if isinstance(seo, dict) else None
    paginator = _state(states, "infiniteVirtualPaginator")
    next_page = _text(paginator.get("nextPage"))

    return OzonSearchResult(
        search_url=search_url,
        query=query,
        title=title,
        items=tuple(items),
        next_page=next_page,
    )


def _is_api_success(status: int) -> bool:
    return status == 200


def _json_payload(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def fetch_search_browser(
    search_url: str,
    *,
    cdp_url: str | None = None,
    headless: bool = False,
    timeout: float = 60.0,
    challenge_timeout: float = 120.0,
    limit: int = 20,
    channel: str | None = None,
    user_data_dir: str | None = None,
    cookie: str | None = None,
) -> OzonSearchResult:
    """Load a category/search page in a browser and read its tile grid via API."""
    api_url = build_search_api_url(search_url)
    _require_playwright()
    limit = max(1, min(int(limit), 100))

    with sync_playwright() as playwright:
        page = None
        context = None
        browser = None
        owned_context = False
        owned_browser = False
        if cdp_url:
            browser = _connect_cdp(playwright, cdp_url)
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
            _add_cookie_header(context, cookie or "", search_url)
            page.set_default_timeout(timeout * 1000)
            if cdp_url:
                try:
                    page.bring_to_front()
                except PlaywrightError:
                    pass

            try:
                page.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=timeout * 1000,
                )
            except PlaywrightTimeoutError:
                pass

            if _page_challenge(page):
                _handle_challenge(
                    page,
                    search_url,
                    challenge_url=None,
                    headless=headless,
                    timeout=challenge_timeout,
                )

            status, text = _fetch_api_in_page(page, api_url)
            if not _is_api_success(status):
                payload = _json_payload(text)
                challenge = _challenge_url(payload)
                if challenge:
                    _handle_challenge(
                        page,
                        search_url,
                        challenge_url=challenge,
                        headless=headless,
                        timeout=challenge_timeout,
                    )
                    status, text = _fetch_api_in_page(page, api_url)
            if not _is_api_success(status):
                if status in {403, 429}:
                    raise OzonSearchError(
                        "Ozon отклонил запрос к поиску (антибот). "
                        "Запусти Chrome с remote debugging и повтори через CDP."
                    )
                raise OzonSearchError(f"Ozon API вернул HTTP {status} для поиска.")

            first = parse_search_json(text, search_url=search_url)
            items = list(first.items)
            next_page = first.next_page
            pages = 1
            max_pages = min(30, math.ceil(limit / 8) + 3)
            while next_page and len(items) < limit and pages < max_pages:
                next_url = urljoin(
                    f"https://{urlparse(search_url).hostname}", next_page
                )
                try:
                    next_api = build_search_api_url(next_url)
                except OzonSearchError:
                    break
                status, text = _fetch_api_in_page(page, next_api)
                if not _is_api_success(status):
                    break
                page_result = parse_search_json(text, search_url=next_url)
                known = {item.sku or item.product_url for item in items}
                for item in page_result.items:
                    key = item.sku or item.product_url
                    if key not in known:
                        items.append(item)
                        known.add(key)
                next_page = page_result.next_page
                pages += 1

            items = items[:limit]
            items = tuple(
                replace(item, position=index + 1) for index, item in enumerate(items)
            )
            return OzonSearchResult(
                search_url=search_url,
                query=first.query,
                title=first.title,
                items=items,
                next_page=next_page,
            )
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
