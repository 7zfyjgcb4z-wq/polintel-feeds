"""Guardian Jobs — returns 403 for non-browser clients (Madgex WAF). Disabled."""
from src.models.job import Job
from src.scrapers.base import BaseScraper


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        self.log.warning("Guardian Jobs blocks non-browser clients (403) — skipping")
        return []
