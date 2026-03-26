"""Smart Thinking Jobs — domain is parked/dead. Disabled in sources.yaml."""
from src.models.job import Job
from src.scrapers.base import BaseScraper


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        self.log.warning("Smart Thinking Jobs domain is parked — skipping")
        return []
