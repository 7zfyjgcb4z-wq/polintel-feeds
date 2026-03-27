"""Third Sector Jobs — scraping not permitted under their ToS. Disabled."""
from src.models.job import Job
from src.scrapers.base import BaseScraper


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        self.log.warning("Third Sector Jobs scraping disabled — not permitted under their ToS")
        return []
