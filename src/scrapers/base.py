import asyncio
import logging
from abc import ABC, abstractmethod

import httpx

from src.models.job import Job

USER_AGENT = "Pol-Intel/1.0 (contact@orison.co)"
REQUEST_DELAY = 2.0  # seconds between page requests

log = logging.getLogger(__name__)

# Status codes that warrant a retry
_RETRY_STATUSES = {429, 503, 502, 504}
_RETRY_BACKOFF = (2.0, 4.0, 8.0)  # seconds to wait before attempt 2, 3, 4


async def fetch_with_retry(
    client: httpx.AsyncClient,
    url: str,
    retries: int = 3,
) -> httpx.Response:
    """GET with exponential backoff on timeout / 429 / 5xx."""
    last_exc: Exception = RuntimeError("No attempts made")
    for attempt in range(retries + 1):
        try:
            response = await client.get(url)
            if response.status_code in _RETRY_STATUSES and attempt < retries:
                wait = _RETRY_BACKOFF[attempt]
                log.warning(f"HTTP {response.status_code} for {url} — retry {attempt + 1}/{retries} in {wait}s")
                await asyncio.sleep(wait)
                continue
            response.raise_for_status()
            return response
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_exc = exc
            if attempt < retries:
                wait = _RETRY_BACKOFF[attempt]
                log.warning(f"{type(exc).__name__} for {url} — retry {attempt + 1}/{retries} in {wait}s")
                await asyncio.sleep(wait)
            else:
                raise
    raise last_exc


class BaseScraper(ABC):
    def __init__(self, source: dict) -> None:
        self.source = source
        self.name: str = source["name"]
        self.url: str = source["url"]
        self.category: str = source.get("category", "general")
        self.country: str = source.get("country", "uk")
        self.log = logging.getLogger(f"scraper.{self.name}")

    @abstractmethod
    async def scrape(self) -> list[Job]:
        """Fetch and return Job objects for this source."""

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        )

    async def _get(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        response = await fetch_with_retry(client, url)
        await asyncio.sleep(REQUEST_DELAY)
        return response
