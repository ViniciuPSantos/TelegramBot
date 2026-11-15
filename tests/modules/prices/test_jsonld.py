import json

import pytest

from assistant.modules.prices.jsonld import extract_quote, parse_price_cents
from assistant.modules.prices.sources import PriceFetchError, PriceQuote


def page(*blocks: object) -> str:
    scripts = "".join(
        f'<script type="application/ld+json">{json.dumps(b)}</script>' for b in blocks
    )
    return f"<html><head>{scripts}</head><body>...</body></html>"


PRODUCT = {
    "@context": "https://schema.org",
    "@type": "Product",
    "name": "SSD Kingston NV3 1TB",
    "offers": {
        "@type": "Offer",
        "price": "1149.90",
        "priceCurrency": "BRL",
        "availability": "https://schema.org/InStock",
    },
}


def test_extracts_product_offer() -> None:
    assert extract_quote(page(PRODUCT)) == PriceQuote("SSD Kingston NV3 1TB", 114990, True)


def test_title_html_entities_are_decoded() -> None:
    product = PRODUCT | {"name": "Mouse &quot;Gamer&quot; &amp; Teclado"}

    assert extract_quote(page(product)).title == 'Mouse "Gamer" & Teclado'


def test_skips_other_blocks_and_broken_json() -> None:
    breadcrumb = {"@type": "BreadcrumbList", "itemListElement": []}
    html = '<script type="application/ld+json">{quebrado</script>' + page(breadcrumb, PRODUCT)

    assert extract_quote(html).price_cents == 114990


def test_finds_product_inside_graph_and_lists() -> None:
    assert extract_quote(page({"@graph": [PRODUCT]})).price_cents == 114990
    assert extract_quote(page([PRODUCT])).price_cents == 114990


def test_aggregate_offer_uses_low_price() -> None:
    product = PRODUCT | {"offers": {"@type": "AggregateOffer", "lowPrice": 935.9}}

    assert extract_quote(page(product)).price_cents == 93590


def test_out_of_stock() -> None:
    offers = PRODUCT["offers"] | {"availability": "http://schema.org/OutOfStock"}

    assert extract_quote(page(PRODUCT | {"offers": offers})).in_stock is False


def test_page_without_product_raises() -> None:
    with pytest.raises(PriceFetchError):
        extract_quote("<html><body>sem dados</body></html>")


@pytest.mark.parametrize(
    ("raw", "cents"),
    [("1149.90", 114990), (1149.9, 114990), ("1.149,90", 114990), ("99,9", 9990), (10, 1000)],
)
def test_parse_price_cents(raw: object, cents: int) -> None:
    assert parse_price_cents(raw) == cents


@pytest.mark.parametrize("raw", ["", "abc", "0", "-5"])
def test_parse_price_cents_rejects_invalid(raw: str) -> None:
    with pytest.raises(PriceFetchError):
        parse_price_cents(raw)
