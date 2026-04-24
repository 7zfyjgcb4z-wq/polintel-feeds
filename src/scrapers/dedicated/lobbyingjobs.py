"""
LobbyingJobs.com scraper.

Dedicated board for lobbying, government relations, advocacy, and public policy.
Job cards use class `article.listing-item__jobs`.  Pagination via ?page=N.

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

    def _parse_page(
        self,
        soup: BeautifulSoup,
        seen_urls: set[str],
        partisan_lean: str | None,
    ) -> list[Job]:
        jobs: list[Job] = []

        cards = soup.select("article.listing-item__jobs")
        if not cards:
            return jobs

        for card in cards:
            title_el = card.select_one(".listing-item__title a, .media-heading a")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            if not title or not href:
                continue
            url = href if href.startswith("http") else f"{BASE}{href}"
            if url in seen_urls:
                continue
            seen_urls.add(url)

            org_el = card.select_one(".listing-item__info--item-company")
            org = org_el.get_text(strip=True) if org_el else self.name

            loc_el = card.select_one(".listing-item__info--item-location")
            location = loc_el.get_text(strip=True) if loc_el else None

            desc_el = card.select_one(".listing-item__desc")
            description = desc_el.get_text(strip=True)[:500] if desc_el else ""

            jobs.append(
                Job(
                    title=title,
                    url=url,
                    organisation=org,
                    description=description,
                    source_name=self.name,
                    category=self.category,
                    country=self.country,
                    location=location,
                    partisan_lean=partisan_lean,
                )
            )

        return jobs
