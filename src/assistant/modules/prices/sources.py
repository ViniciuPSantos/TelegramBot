"""Fonte de preço? cada loja suportada e um PriceSource"""

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class PriceQuote:
    title: str
    price_cents: int
    in_stock: bool


class PriceFetchError(Exception):
    """Nao foi possivel obter o preco (pagina mudou, produto sem preco, erro de rede...)."""


class StoreBlockedError(PriceFetchError):
    """A loja recusou a requisicao (403/429/503): parar de insistir"""


class UnsupportedStoreError(ValueError):
    """O link não pertence a nenhuma loja suportada."""


class PriceSource(Protocol):
    name: str

    def supports(self, url: str) -> bool: ...

    async def fetch(self, url: str) -> PriceQuote: ...


def host_matches(url: str, domains: tuple[str, ...]) -> bool:
    """True se a URL e http(S) e o host e um dos dominios/subdominios"""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    host = parts.hostname.lower()
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def find_source(sources: list[PriceSource], url: str) -> PriceSource:
    for source in sources:
        if source.supports(url):
            return source
    raise UnsupportedStoreError("Loja nao suportada.")
