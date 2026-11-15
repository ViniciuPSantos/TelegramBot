import httpx
import pytest

from assistant.modules.prices.sources import (
    PriceFetchError,
    StoreBlockedError,
    UnsupportedStoreError,
    find_source,
    host_matches,
)
from assistant.modules.prices.stores import JsonLdSource

KABUM = ("kabum.com.br",)
PRODUCT_URL = "https://www.kabum.com.br/produto/1/ssd"
PRODUCT_HTML = (
    '<script type="application/ld+json">'
    '{"@type": "Product", "name": "SSD", "offers": {"price": "100.00"}}'
    "</script>"
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.kabum.com.br/produto/1", True),
        ("https://kabum.com.br/produto/1", True),
        ("http://KABUM.com.br/x", True),
        ("https://evilkabum.com.br/x", False),
        ("https://kabum.com.br.evil.com/x", False),
        ("ftp://kabum.com.br/x", False),
        ("kabum.com.br/produto/1", False),
    ],
)
def test_host_matches(url: str, expected: bool) -> None:
    assert host_matches(url, KABUM) is expected


def make_source(handler: httpx.MockTransport) -> JsonLdSource:
    client = httpx.AsyncClient(transport=handler, follow_redirects=True)
    return JsonLdSource(client, name="Kabum", domains=KABUM)


async def test_fetch_returns_quote() -> None:
    source = make_source(httpx.MockTransport(lambda req: httpx.Response(200, text=PRODUCT_HTML)))

    quote = await source.fetch(PRODUCT_URL)

    assert (quote.title, quote.price_cents) == ("SSD", 10000)


@pytest.mark.parametrize("status", [403, 429, 503])
async def test_blocking_status_raises_store_blocked(status: int) -> None:
    source = make_source(httpx.MockTransport(lambda req: httpx.Response(status)))

    with pytest.raises(StoreBlockedError):
        await source.fetch(PRODUCT_URL)


async def test_other_errors_raise_fetch_error() -> None:
    source = make_source(httpx.MockTransport(lambda req: httpx.Response(500)))

    with pytest.raises(PriceFetchError) as exc_info:
        await source.fetch(PRODUCT_URL)
    assert not isinstance(exc_info.value, StoreBlockedError)


async def test_redirect_outside_store_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.kabum.com.br":
            return httpx.Response(302, headers={"Location": "https://outro-site.com/"})
        return httpx.Response(200, text=PRODUCT_HTML)

    with pytest.raises(PriceFetchError, match="redirecionou"):
        await make_source(httpx.MockTransport(handler)).fetch(PRODUCT_URL)


def test_find_source() -> None:
    source = make_source(httpx.MockTransport(lambda req: httpx.Response(200)))

    assert find_source([source], PRODUCT_URL) is source
    with pytest.raises(UnsupportedStoreError):
        find_source([source], "https://www.terabyteshop.com.br/produto/1")
