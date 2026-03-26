"""Bond Jobs — Salesforce Aura SPA, not scrapeable without Playwright + session tokens. Disabled."""
from src.models.job import Job
from src.scrapers.base import BaseScraper


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        self.log.warning("Bond Jobs uses Salesforce Aura SPA — not yet implemented")
        return []
