"""
Emplois Politiques scraper.

WIX-hosted blog at emplois-politiques.fr where job postings are published as
blog posts.  The WIX Pro Gallery widget renders the three most recent posts
server-side (SSR); subsequent items are JS-loaded and not accessible without
Playwright.

The SSR slice always reflects the latest job posts, is zero-API, and updates
on every run.  WIX Pro Gallery markup uses stable semantic class names
("gallery-item-container", "pro-gallery") alongside hashed CSS module names
that may change; selectors use only the stable ones.

Description: extracted via a.find_next_sibling("div") to avoid reliance on
hashed WIX CSS class names for the description container.
"""
from __future__ import annotations

import asyncio

import httpx
from bs4 import BeautifulSoup

from src.models.job import Job
from src.scrapers.base import BaseScraper, USER_AGENT, REQUEST_DELAY

LISTING_URL = "https://www.emplois-politiques.fr/les-offres-d-emplois"


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            try:
                r = await client.get(LISTING_URL)
                r.raise_for_status()
                await asyncio.sleep(REQUEST_DELAY)
            except httpx.HTTPError as exc:
                self.log.error(f"Fetch error: {exc}")
                raise

        soup = BeautifulSoup(r.text, "lxml")
        jobs: list[Job] = []
        seen_urls: set[str] = set()

        for card in soup.select("div.gallery-item-container"):
            a = card.select_one("a[href]")
            if not a:
                continue
            url = a.get("href", "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            # Title: h2 inside the title anchor
            h2 = a.find("h2")
            title = h2.get_text(strip=True) if h2 else a.get_text(strip=True)
            if not title:
                continue

            # Description: sibling div following the title anchor (stable structure;
            # avoids dependency on WIX-hashed CSS class names in the container).
            desc_div = a.find_next_sibling("div")
            description = desc_div.get_text(strip=True) if desc_div else ""

            jobs.append(
                Job(
                    title=title,
                    url=url,
                    organisation=self.name,
                    description=description,
                    source_name=self.name,
                    category=self.category,
                    country=self.country,
                    location=None,
                )
            )

        self.log.info(f"Total: {len(jobs)} jobs (SSR slice — latest posts only)")
        return jobs
