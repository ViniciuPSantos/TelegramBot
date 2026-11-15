import httpx

from assistant.modules.prices.sources import PriceFetchError, StoreBlockedError

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_BLOCKED_STATUS = {403, 429, 503}


def build_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "pt-BR,pt;q=0.9",
        },
        timeout=httpx.Timeout(20.0),
        follow_redirects=True,
    )


async def fetch_html(client: httpx.AsyncClient, url: str) -> httpx.Response:
    try:
        response = await client.get(url)
    except httpx.HTTPError as exc:
        raise PriceFetchError(f"Falha de rede: {type(exc).__name__}") from exc
    if response.status_code in _BLOCKED_STATUS:
        raise StoreBlockedError(f"A loja recusou a requisição HTTP {response.status_code}")
    if response.status_code != 200:
        raise PriceFetchError(f"Resposta inesperada da loja (HTTP {response.status_code})")
    return response
