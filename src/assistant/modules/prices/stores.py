import httpx

from assistant.modules.prices.http import fetch_html
from assistant.modules.prices.jsonld import extract_quote
from assistant.modules.prices.sources import PriceFetchError, PriceQuote, PriceSource, host_matches


class JsonLdSource:
    """Loja que publica o preço em JSON-LD: não precisa de código específico."""

    def __init__(self, client: httpx.AsyncClient, *, name: str, domains: tuple[str, ...]) -> None:
        self.name = name
        self._client = client
        self._domains = domains

    def supports(self, url: str) -> bool:
        return host_matches(url, self._domains)

    async def fetch(self, url: str) -> PriceQuote:
        response = await fetch_html(self._client, url)
        # Um redirect pode levar a outro site (ou a uma página de verificação): não confia.
        if not self.supports(str(response.url)):
            raise PriceFetchError("A loja redirecionou para fora do site.")
        return extract_quote(response.text)


def build_sources(client: httpx.AsyncClient) -> list[PriceSource]:
    # Terabyte também usa JSON-LD, mas bloqueia IPs de datacenter (testado na VPS: 403).
    return [
        JsonLdSource(client, name="Kabum", domains=("kabum.com.br",)),
    ]
