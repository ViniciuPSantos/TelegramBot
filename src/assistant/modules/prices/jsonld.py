"""Extrai o preco do JSON-LD que muitas lojas embutem na pagina"""

import json
import re
from collections.abc import Iterator
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from html import unescape
from typing import Any

from assistant.modules.prices.sources import PriceFetchError, PriceQuote

_LD_JSON_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_IN_STOCK = ("InStock", "LimitedAvailability", "OnlineOnly", "InStoreOnly")


def extract_quote(html: str) -> PriceQuote:
    for node in _json_ld_nodes(html):
        if not _is_product(node):
            continue
        offer = _first_offer(node.get("offers"))
        if offer is None:
            continue
        raw_price = offer.get("price", offer.get("lowPrice"))
        if raw_price is None:
            continue
        return PriceQuote(
            title=unescape(str(node.get("name", ""))).strip(),
            price_cents=parse_price_cents(raw_price),
            in_stock=_is_in_stock(offer.get("availability")),
        )
    raise PriceFetchError("Preço não encontrado na página.")


def parse_price_cents(value: object) -> int:
    """'1149.90', 1149.9, '1.149,90' -> 114990."""
    text = str(value).strip()
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise PriceFetchError(f"Preço inválido: {value!r}") from exc
    if amount <= 0:
        raise PriceFetchError(f"Preço inválido: {value!r}")
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _json_ld_nodes(html: str) -> Iterator[dict[str, Any]]:
    for block in _LD_JSON_RE.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue

        stack = data if isinstance(data, list) else [data]
        for item in stack:
            if isinstance(item, dict):
                yield item
                graph = item.get("@graph")
                if isinstance(graph, list):
                    yield from (g for g in graph if isinstance(g, dict))


def _is_product(node: dict[str, Any]) -> bool:
    kind = node.get("@type")
    kinds = kind if isinstance(kind, list) else [kind]
    return "Product" in kinds


def _first_offer(offers: object) -> dict[str, Any] | None:
    if isinstance(offers, list):
        offers = offers[0] if offers else None
    return offers if isinstance(offers, dict) else None


def _is_in_stock(availability: object) -> bool:
    if availability is None:
        return True
    return str(availability).rsplit("/", 1)[-1] in _IN_STOCK
