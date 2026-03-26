"""Escape the City — Algolia/Vue SPA. Needs Algolia API key from browser session. Disabled."""
from src.models.job import Job
from src.scrapers.base import BaseScraper


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        self.log.warning("Escape the City uses Algolia SPA — not yet implemented")
        return []
