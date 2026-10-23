from __future__ import annotations

import json
import os
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from urllib.parse import urlencode, urlparse

import httpx

from ozon_parser.fetch import OzonFetchError
from ozon_parser.parser import OzonProduct, OzonProductParseError
from ozon_parser.urls import is_ozon_host

API_PATH = "/api/entrypoint-api.bx/page/json/v2"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36"
)
OZON_COOKIE_ENV = "__Secure-ab-group=96; __Secure-user-id=0; __Secure-ext_xcid=607b2f4fa057500195403aa00b0721a1; x-o3-timezone=-180; __Secure-access-token=12.0.yskuO-pIRLaNrVQ4OtehyQ.96.ASd-yQGDIsMYhyUD4Lcr9eLiN9enMCkVkskC86nrUz2ACl-YFu5aP-xJgd3Rbllmw5__BJyb5x9_RjYz8pP4kUnakKHpF8rwNXT8AgyjhGXxOC0wKH96EswMd9YYhujaiw..20261022190655.0.hs9L3GADypV3hiFYXLXqHzfN5_2HvNORzPhHDcchKvs.14592acf18e3bbf; __Secure-refresh-token=12.0.yskuO-pIRLaNrVQ4OtehyQ.96.ASd-yQGDIsMYhyUD4Lcr9eLiN9enMCkVkskC86nrUz2ACl-YFu5aP-xJgd3Rbllmw5__BJyb5x9_RjYz8pP4kUnakKHpF8rwNXT8AgyjhGXxOC0wKH96EswMd9YYhujaiw..20261022190655.0.i9-JKob1gvEdHFrN6gowIxwtn1VcU29B0526evnM8QQ.18b355e638279183e; xcid=17c7507ee2baccf894f30cf0196bfe51; ADDRESSBOOKBAR_WEB_CLARIFICATION=1792688816; __Secure-ETC=d5a918466f3faabacf8bd5f8ea0abc19; abt_data=7.th9kTANwlc4zbN8SbFmC-8IXYN-acBLjaxS30-MgLDF_NdLE-nRDZ0yUgn6mfTzqnCc6ppUa_4VJ35KKADIJT6DUvF2QDBa-tZGgQJsoUmslg73uze_Mxhvxaqvq1wJtDtO3VptkYa6_l_0H41LjTdUhzeAY9taU6eErUcm-oj_A8-da7Q6soFJOXowgSDB_GmlUw_E3GJetJf-T4xzzLgAFeKsTI_as25GkpHYWLky8qcAc-RhB9trL0dFT1Y5x_Fs77Wq84GF1OhaRAGJRQwF2sOYEVtpqP27i4cMLmHT7GEtlyanQh19UP870Q6Il84pRlVOQTFN_HZSUakEHj5Mgw580pLji12Pxj5dTAueDvNlu3YzEshBMb-yZCeWJkMiWpXsWStn5mhKCPut7vahx5gJqVxPdtfte8WxaeE4382sew61fmTKf4vYiML1Cm5LplUJ7TmAfB85ND3MbOx85soyOX5aJAY7SZHv4BoIakcfm_hdom8cKZ-CIbM1l0giffmmGLMsjzF55CQ4RCMn1i9eJNfcP2x9axu4dLuzz7sLpqebDa4OtkgqYY0hJYw709QZin6SRCtflZbfk-Q1kOIAKhBSCijqTt6PtycAKfdwnNU4cbC58KEVnh0sAwK4Fu1ZM8ZT4VtaWj0gMv2oPVns8k1iGHBpT1l7fdzDGoBdpKgkDWa33BTMNUeTGalowgT4Q0ykmTCo"

SCHEMA_IN_STOCK = "https://schema.org/InStock"
SCHEMA_OUT_OF_STOCK = "https://schema.org/OutOfStock"

_CURRENCY_BY_SYMBOL = (
    ("₽", "RUB"),
    ("₸", "KZT"),
    ("₴", "UAH"),
    ("₾", "GEL"),
    ("֏", "AMD"),
    ("£", "GBP"),
    ("€", "EUR"),
    ("$", "USD"),
    ("сум", "UZS"),
)
_CURRENCY_CODES = {
    "RUB",
    "KZT",
    "BYN",
    "UZS",
    "UAH",
    "GEL",
    "AMD",
    "USD",
    "EUR",
    "GBP",
    "CNY",
}


def _load_json(payload: Any) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        return dict(payload)

    if isinstance(payload, (bytes, bytearray)):
        try:
            text = bytes(payload).decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise OzonProductParseError(
                "Ответ Ozon API не является UTF-8 JSON."
            ) from exc
    elif isinstance(payload, str):
        text = payload.lstrip("\ufeff")
    else:
        raise OzonProductParseError(
            f"Ожидался JSON-объект Ozon API, получено: {type(payload).__name__}."
        )

    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[A-Za-z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # Responses copied from DevTools sometimes keep a stray trailing backtick.
    text = text.strip("`").strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OzonProductParseError(
            f"Не удалось разобрать JSON ответа Ozon: {exc}."
        ) from exc

    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise OzonProductParseError(
                "Ответ Ozon API содержит строку, а не JSON-объект."
            ) from exc

    if not isinstance(data, dict):
        raise OzonProductParseError("Ответ Ozon API должен быть JSON-объектом.")
    return data


def _decode_state(value: Any) -> dict[str, Any]:
    """Widget states are JSON strings in Ozon responses, but may already be dicts."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _decode_states(raw_states: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}
    for key, value in raw_states.items():
        state = _decode_state(value)
        if state:
            states[key] = state
    return states


def _state(states: Mapping[str, dict[str, Any]], *prefixes: str) -> dict[str, Any]:
    for prefix in prefixes:
        for key, value in states.items():
            if key == prefix or key.startswith(f"{prefix}-"):
                return value
    return {}


def _rich_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict) and item.get("type") in {
                "newLine",
                "lineBreak",
                "br",
            }:
                parts.append("\n")
            else:
                parts.append(_rich_text(item))
        return "".join(parts).strip()
    if isinstance(value, dict):
        for key in ("text", "content", "value"):
            if isinstance(value.get(key), str):
                return value[key].strip()
        for key in ("textRs", "body", "items", "children", "textAtom"):
            if key in value:
                return _rich_text(value[key])
    return ""


def _text(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (str, int, float, Decimal)):
        text = str(value).strip()
        return text or None
    if isinstance(value, (dict, list)):
        return _rich_text(value) or None
    return None


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, dict):
        for key in ("price", "value", "amount", "text"):
            if key in value:
                return _decimal(value[key])
        return None
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
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    cleaned = re.sub(r"\D", "", str(value))
    return int(cleaned) if cleaned else None


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "in stock", "instock"}:
            return True
        if normalized in {"false", "0", "no", "out of stock", "outofstock"}:
            return False
    return None


def _currency(*values: Any) -> str | None:
    for value in values:
        text = _text(value)
        if not text:
            continue
        for symbol, code in _CURRENCY_BY_SYMBOL:
            if symbol in text:
                return code
        upper = text.strip().upper()
        if upper in _CURRENCY_CODES:
            return upper
    return None


def _characteristics(state: Mapping[str, Any]) -> dict[str, str]:
    items = state.get("characteristics")
    if not isinstance(items, list):
        return {}
    result: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _text(item.get("title"))
        raw_values = item.get("values")
        if raw_values is None:
            raw_values = item.get("value")
        values = raw_values if isinstance(raw_values, list) else [raw_values]
        rendered = [text for text in (_text(value) for value in values) if text]
        if title and rendered:
            result[title] = ", ".join(rendered)
    return result


def _images(gallery: Mapping[str, Any]) -> tuple[str, ...]:
    urls: list[str] = []

    def add(value: Any) -> None:
        url = _text(value)
        if not url:
            return
        if url.startswith("//"):
            url = f"https:{url}"
        if url not in urls:
            urls.append(url)

    images = gallery.get("images")
    if isinstance(images, list):
        for item in images:
            if isinstance(item, dict):
                add(item.get("src") or item.get("image") or item.get("url"))
            else:
                add(item)
    add(gallery.get("coverImage"))
    return tuple(urls)


def _canonical_url(data: Mapping[str, Any]) -> str | None:
    seo = data.get("seo")
    if not isinstance(seo, dict):
        return None
    links = seo.get("link")
    if not isinstance(links, list):
        return None
    for link in links:
        if (
            isinstance(link, dict)
            and link.get("rel") == "canonical"
            and isinstance(link.get("href"), str)
        ):
            return link["href"]
    return None


def _currency_from_url(url: str | None) -> str | None:
    if not url:
        return None
    host = (urlparse(url).hostname or "").lower()
    domains = (
        ("ozon.ru", "RUB"),
        ("ozon.kz", "KZT"),
        ("ozon.by", "BYN"),
        ("ozon.uz", "UZS"),
    )
    for domain, code in domains:
        if host == domain or host.endswith(f".{domain}"):
            return code
    return None


def _seller(
    states: Mapping[str, dict[str, Any]], sticky: Mapping[str, Any]
) -> str | None:
    current = _state(states, "webCurrentSeller")
    seller_cell = current.get("sellerCell")
    if isinstance(seller_cell, dict):
        center = seller_cell.get("centerBlock")
        if isinstance(center, dict):
            name = _text(center.get("title"))
            if name:
                return name
    sticky_seller = sticky.get("seller")
    if isinstance(sticky_seller, dict):
        return _text(sticky_seller.get("name"))
    return None


def _sku(
    states: Mapping[str, dict[str, Any]],
    data: Mapping[str, Any],
    source_url: str | None,
) -> str | None:
    candidates = [
        _state(states, "webDetailSKU").get("copyText"),
        _state(states, "webProductMainWidget").get("sku"),
        _state(states, "webGallery").get("sku"),
        _state(states, "webStickyProducts").get("sku"),
    ]
    page_info = data.get("pageInfo")
    if isinstance(page_info, dict):
        analytics = page_info.get("analyticsInfo")
        if isinstance(analytics, dict):
            candidates.append(analytics.get("sku"))
    for candidate in candidates:
        sku = _text(candidate)
        if sku:
            return sku
    if source_url:
        match = re.search(r"-(\d+)/?(?:\?|$)", urlparse(source_url).path)
        if match:
            return match.group(1)
    return None


def parse_product_json(
    payload: Any,
    source_url: str | None = None,
) -> OzonProduct:
    """Extract product fields from an `entrypoint-api.bx/page/json/v2` response.

    ``payload`` may be a dict, a JSON string, or raw bytes, so the function can
    consume both a live response and a file saved from browser DevTools.
    """
    data = _load_json(payload)
    canonical_url = _canonical_url(data)
    effective_url = source_url or canonical_url

    incident = data.get("incidentId") or data.get("incident_id")
    if incident:
        raise OzonProductParseError(
            "Ozon вернул антибот-заглушку вместо карточки "
            f"(incidentId: {incident}). Обычный HTTP-клиент не прошёл проверку Ozon."
        )

    raw_states = data.get("widgetStates")
    if not isinstance(raw_states, dict):
        raise OzonProductParseError(
            "В JSON нет поля widgetStates — это не ответ Ozon entrypoint-api."
        )
    states = _decode_states(raw_states)
    if not states:
        raise OzonProductParseError(
            "Поле widgetStates пустое или не содержит JSON-виджетов."
        )

    heading = _state(states, "webProductHeading")
    sticky = _state(states, "webStickyProducts")
    price_state = _state(states, "webPrice")
    score_state = _state(states, "webReviewProductScore")
    gallery = _state(states, "webGallery")
    details = _state(states, "webShortCharacteristics")

    name = _text(heading.get("title")) or _text(sticky.get("name"))

    price = _decimal(price_state.get("price"))
    card_price = _decimal(price_state.get("cardPrice"))
    if price is None:
        price = card_price
    original_price = _decimal(price_state.get("originalPrice"))
    currency = _currency(
        price_state.get("price"),
        price_state.get("cardPrice"),
        price_state.get("originalPrice"),
        price_state.get("currency"),
    )
    if currency is None:
        currency = _currency_from_url(effective_url)

    in_stock = _boolean(price_state.get("isAvailable"))
    if in_stock is None:
        offer = _state(states, "webSale").get("offer")
        if isinstance(offer, dict):
            in_stock = _boolean(offer.get("isAvailable"))
    if in_stock is None:
        unavailable = _boolean(gallery.get("isUnavailable"))
        if unavailable is not None:
            in_stock = not unavailable
    availability = None
    if in_stock is True:
        availability = SCHEMA_IN_STOCK
    elif in_stock is False:
        availability = SCHEMA_OUT_OF_STOCK

    rating = _decimal(score_state.get("totalScore"))
    if rating is None:
        rating = _decimal(_state(states, "webSingleProductScore").get("text"))
    review_count = _integer(score_state.get("reviewsCount"))

    characteristics = _characteristics(details)
    brand_state = _state(states, "webBrand")
    brand = _text(brand_state.get("title")) or _text(brand_state.get("name"))
    if not brand:
        brand = characteristics.get("Бренд") or characteristics.get("Brand")

    description_state = _state(states, "webDescription")
    description = _text(
        description_state.get("text")
        or description_state.get("textRs")
        or description_state.get("body")
    )

    image_urls = _images(gallery)
    sku = _sku(states, data, source_url)
    seller = _seller(states, sticky)

    if not any((name, price, sku, image_urls, characteristics)):
        raise OzonProductParseError(
            "В ответе entrypoint-api не найдены поля карточки товара. "
            "Ozon мог вернуть другую страницу или изменить структуру виджетов."
        )

    return OzonProduct(
        source_url=effective_url,
        name=name,
        description=description,
        price=price,
        currency=currency,
        availability=availability,
        rating=rating,
        review_count=review_count,
        sku=sku,
        image_urls=image_urls,
        original_price=original_price,
        card_price=card_price,
        in_stock=in_stock,
        seller=seller,
        brand=brand,
        characteristics=characteristics,
    )


def build_api_url(product_url: str) -> str:
    """Build the `entrypoint-api` URL Ozon's PDP uses to load its widgets."""
    parsed = urlparse(product_url)
    if parsed.scheme not in {"http", "https"} or not is_ozon_host(parsed.hostname):
        raise OzonFetchError("Укажи ссылку на карточку товара на домене Ozon.")
    if not parsed.path.startswith("/product/"):
        raise OzonFetchError("Ссылка должна вести на карточку товара: /product/...")

    target = parsed.path
    if parsed.query:
        target = f"{target}?{parsed.query}"
    query = urlencode({"url": target})
    return f"https://{parsed.hostname}{API_PATH}?{query}"


def _antibot_message(status_code: int) -> str:
    return (
        f"Ozon отклонил запрос к API (HTTP {status_code}, антибот-защита). "
        "Обычный HTTP-клиент не проходит проверку Ozon. "
        "Сохрани ответ entrypoint-api из DevTools и передай его через --json "
        "или укажи cookie браузера через --cookie / OZON_COOKIE (может помочь, "
        "но Ozon всё равно может отклонить запрос)."
    )


def fetch_product_api(
    product_url: str,
    timeout: float = 20.0,
    cookie: str | None = None,
) -> OzonProduct:
    """Fetch a product through Ozon's public `entrypoint-api` JSON endpoint.

    The request uses ordinary browser-like headers. If Ozon answers with its
    anti-bot challenge, a clear error is raised instead of trying to solve it.
    """
    api_url = build_api_url(product_url)
    cookie = cookie if cookie is not None else os.environ.get(OZON_COOKIE_ENV)
    headers = {
        "User-Agent": os.environ.get("OZON_USER_AGENT", DEFAULT_USER_AGENT),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Referer": product_url,
        "x-o3-app-name": "dweb_client",
    }
    if cookie:
        headers["Cookie"] = cookie

    try:
        with httpx.Client(
            follow_redirects=True, timeout=timeout, headers=headers
        ) as client:
            response = client.get(api_url)
    except httpx.HTTPError as exc:
        raise OzonFetchError(f"Не удалось запросить Ozon API: {exc}") from exc

    if response.status_code in {403, 429}:
        raise OzonFetchError(_antibot_message(response.status_code))
    if response.status_code >= 400:
        raise OzonFetchError(f"Ozon API вернул HTTP {response.status_code}.")

    try:
        payload = response.json()
    except ValueError as exc:
        snippet = response.text.lstrip()[:120].replace("\n", " ")
        if snippet.startswith("<"):
            raise OzonFetchError(
                "Ozon API вернул HTML вместо JSON (антибот или страница проверки). "
                "Сохрани корректный ответ из DevTools и используй --json."
            ) from exc
        raise OzonFetchError(f"Ozon API вернул не JSON: {snippet!r}") from exc

    if isinstance(payload, dict) and (
        payload.get("incidentId") or payload.get("incident_id")
    ):
        raise OzonFetchError(_antibot_message(response.status_code))

    return parse_product_json(payload, source_url=product_url)
