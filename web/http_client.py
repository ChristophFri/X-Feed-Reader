"""Shared httpx.AsyncClient for connection pooling across the web app."""

import httpx

from web.constants import HTTP_CONNECT_TIMEOUT, HTTP_TOTAL_TIMEOUT

_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """Return the shared httpx.AsyncClient. Falls back to creating one if not initialized."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(HTTP_TOTAL_TIMEOUT, connect=HTTP_CONNECT_TIMEOUT))
    return _client


async def init_http_client() -> None:
    """Initialize the shared client. Call during app startup."""
    global _client
    _client = httpx.AsyncClient(timeout=httpx.Timeout(HTTP_TOTAL_TIMEOUT, connect=HTTP_CONNECT_TIMEOUT))


async def close_http_client() -> None:
    """Close the shared client. Call during app shutdown."""
    global _client
    if _client:
        await _client.aclose()
        _client = None
