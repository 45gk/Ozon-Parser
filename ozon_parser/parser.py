from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any


class OzonProductParseError(ValueError):
    """Raised when the supplied page or API payload contains no product data."""


@dataclass(frozen=True)
class OzonProduct:
    source_url: str | None = None
    name: str | None = None
    description: str | None = None
    price: Decimal | None = None
    currency: str | None = None
    availability: str | None = None
    rating: Decimal | None = None
    review_count: int | None = None
    sku: str | None = None
    image_urls: tuple[str, ...] = ()
    original_price: Decimal | None = None
    card_price: Decimal | None = None
    in_stock: bool | None = None
    seller: str | None = None
    brand: str | None = None
    characteristics: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for name in ("price", "rating", "original_price", "card_price"):
            value = getattr(self, name)
            result[name] = str(value) if value is not None else None
        result["image_urls"] = list(self.image_urls)
        return result


class _PageMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.scripts: list[tuple[str, str]] = []
        self.title_parts: list[str] = []
        self._script_type: str | None = None
        self._script_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value for key, value in attrs if value is not None}
        if tag.lower() == "meta":
            key = attributes.get("property") or attributes.get("name")
            content = attributes.get("content")
            if key and content:
                self.meta[key.lower()] = content.strip()
        elif tag.lower() == "script":
            self._script_type = attributes.get("type", "").lower()
            self._script_parts = []
        elif tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._script_type is not None:
            self.scripts.append((self._script_type, "".join(self._script_parts)))
            self._script_type = None
            self._script_parts = []
        elif tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._script_type is not None:
            self._script_parts.append(data)
        if self._in_title:
            self.title_parts.append(data)


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk(nested)


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float, Decimal)):
        normalized = str(value).strip()
        return normalized or None
    if isinstance(value, dict):
        return _as_text(value.get("name") or value.get("@id") or value.get("url"))
    return None


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    cleaned = re.sub(r"[^\d,.-]", "", str(value)).replace(",", ".")
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _product_type(value: Any) -> bool:
    kinds = value if isinstance(value, list) else [value]
    return any(str(kind).rsplit("/", 1)[-1].lower() == "product" for kind in kinds)


def _images(value: Any) -> tuple[str, ...]:
    values = value if isinstance(value, list) else [value]
    urls = []
    for item in values:
        url = _as_text(item)
        if url and url not in urls:
            urls.append(url)
    return tuple(urls)


def _first_product(documents: list[Any]) -> dict[str, Any] | None:
    for document in documents:
        for node in _walk(document):
            if _product_type(node.get("@type")):
                return node
    return None


def _first_offer(product: dict[str, Any]) -> dict[str, Any]:
    offers = product.get("offers")
    if isinstance(offers, list):
        return next((offer for offer in offers if isinstance(offer, dict)), {})
    return offers if isinstance(offers, dict) else {}


def parse_product_html(html: str, source_url: str | None = None) -> OzonProduct:
    """Extract common product fields from Ozon HTML metadata and JSON-LD.

    The function is intentionally independent from HTTP fetching, so saved pages
    and HTML fixtures can be parsed without contacting Ozon.
    """
    page = _PageMetadataParser()
    page.feed(html)

    documents: list[Any] = []
    for script_type, content in page.scripts:
        if "ld+json" not in script_type or not content.strip():
            continue
        try:
            documents.append(json.loads(content))
        except json.JSONDecodeError:
            continue

    product = _first_product(documents) or {}
    offer = _first_offer(product)
    aggregate_rating = product.get("aggregateRating")
    aggregate_rating = aggregate_rating if isinstance(aggregate_rating, dict) else {}

    meta = page.meta
    name = (
        _as_text(product.get("name"))
        or meta.get("og:title")
        or "".join(page.title_parts).strip()
    )
    description = _as_text(product.get("description")) or meta.get("og:description")
    price = _as_decimal(offer.get("price") or offer.get("lowPrice"))
    price = (
        price if price is not None else _as_decimal(meta.get("product:price:amount"))
    )
    currency = _as_text(offer.get("priceCurrency")) or meta.get(
        "product:price:currency"
    )
    availability = _as_text(offer.get("availability")) or meta.get(
        "product:availability"
    )
    rating = _as_decimal(aggregate_rating.get("ratingValue"))
    review_count_value = aggregate_rating.get("reviewCount") or aggregate_rating.get(
        "ratingCount"
    )
    try:
        review_count = (
            int(str(review_count_value).replace(" ", ""))
            if review_count_value is not None
            else None
        )
    except ValueError:
        review_count = None

    images = _images(product.get("image"))
    if not images and meta.get("og:image"):
        images = (meta["og:image"],)

    sku = _as_text(product.get("sku") or product.get("productID"))
    if not any((name, price, description, images, sku)):
        raise OzonProductParseError(
            "Не удалось найти данные карточки в JSON-LD или Open Graph. "
            "Ozon мог отдать упрощённую, заблокированную или изменённую страницу."
        )

    return OzonProduct(
        source_url=source_url,
        name=name or None,
        description=description,
        price=price,
        currency=currency,
        availability=availability,
        rating=rating,
        review_count=review_count,
        sku=sku,
        image_urls=images,
    )
