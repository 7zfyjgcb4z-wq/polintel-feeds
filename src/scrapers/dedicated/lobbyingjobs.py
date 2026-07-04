"""
LobbyingJobs.com scraper.

Dedicated board for lobbying, government relations, advocacy, and public policy.
Site was rebuilt on a Tailwind front end (re-derived 2026-07-04; the prior
`article.listing-item__jobs` markup no longer exists). Job cards are now
`a[href*="/job/"]` anchors; see _parse_page for the per-field selectors.
Pagination via ?page=N.

Cap: 200 jobs, max 10 pages.
"""
from __future__ import annotations

import asyncio

import httpx
from bs4 import BeautifulSoup

from src.models.job import Job
from src.scrapers.base import BaseScraper, USER_AGENT, REQUEST_DELAY

BASE = "https://lobbyingjobs.com"
JOBS_PATH = "/jobs"
MAX_PAGES = 10
JOB_CAP = 200


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        partisan_lean = self.source.get("partisan_lean")
        jobs: list[Job] = []
        seen_urls: set[str] = set()

        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            for page_num in range(1, MAX_PAGES + 1):
                url = f"{BASE}{JOBS_PATH}" if page_num == 1 else f"{BASE}{JOBS_PATH}?page={page_num}"
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    await asyncio.sleep(REQUEST_DELAY)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404 and page_num > 1:
                        break
                    self.log.error(f"HTTP {exc.response.status_code} fetching {url}")
                    if page_num == 1:
                        raise
                    break
                except httpx.HTTPError as exc:
                    self.log.error(f"Fetch error {url}: {exc}")
                    if page_num == 1:
                        raise
                    break

                soup = BeautifulSoup(r.text, "lxml")
                page_jobs = self._parse_page(soup, seen_urls, partisan_lean)

                if not page_jobs:
                    break

                jobs.extend(page_jobs)
                self.log.debug(f"Page {page_num}: {len(page_jobs)} jobs")

                if len(jobs) >= JOB_CAP:
                    break

        self.log.info(f"Total: {len(jobs)} jobs")
        return jobs[:JOB_CAP]

    # Card container: a[href*="/job/"] anchor (~20 per page).
    CARD_SELECTOR = 'a[href*="/job/"]'
    # Title: <h2 class="mt-0.5 font-semibold text-gray-900 ...">, the only h2 in the card.
    TITLE_SELECTOR = "h2"
    # Company: <p class="text-xs font-medium text-gray-500"> above the title.
    COMPANY_SELECTOR = "p.text-xs.font-medium.text-gray-500"
    # Location: first <span> in the "div.mt-2" location/tag row. Multi-location
    # postings render as a single span with " | "-separated text (not multiple
    # spans), so .select_one is correct here, not .select.
    LOCATION_SELECTOR = "div.mt-2 span"
    # No summary/description text exists on the card in the new markup — leave
    # description empty and let Stage 3 enrichment fetch the detail page.

    def _parse_page(
        self,
        soup: BeautifulSoup,
        seen_urls: set[str],
        partisan_lean: str | None,
    ) -> list[Job]:
        jobs: list[Job] = []

        cards = soup.select(self.CARD_SELECTOR)
        if not cards:
            self.log.warning(
                f"{self.name}: card selector {self.CARD_SELECTOR!r} matched 0 elements — "
                "page markup may have changed"
            )
            return jobs

        for card in cards:
            title_el = card.select_one(self.TITLE_SELECTOR)
            href = card.get("href", "")
            if not title_el or not href:
                continue

            title = title_el.get_text(strip=True)
            if not title:
                continue
            url = href if href.startswith("http") else f"{BASE}{href}"
            if url in seen_urls:
                continue
            seen_urls.add(url)

            org_el = card.select_one(self.COMPANY_SELECTOR)
            org = org_el.get_text(strip=True) if org_el else self.name

            loc_el = card.select_one(self.LOCATION_SELECTOR)
            location = loc_el.get_text(strip=True) if loc_el else None

            jobs.append(
                Job(
                    title=title,
                    url=url,
                    organisation=org,
                    description="",
                    source_name=self.name,
                    category=self.category,
                    country=self.country,
                    location=location,
                    partisan_lean=partisan_lean,
                )
            )

        return jobs
