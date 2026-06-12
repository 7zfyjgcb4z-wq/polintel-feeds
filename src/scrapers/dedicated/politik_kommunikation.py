"""
Politik-Kommunikation Jobs scraper.

Job board at jobs.politik-kommunikation.de for public-affairs and political-
communication roles.  Next.js SSR — job cards render server-side as
<a class="job-listing">.  URL pagination via ?page=N.

Listing URL: /stellen-beruf/bundestag-ministerien-verwaltung
(resolves from the old /stellen-beruf/parlament-regierung 307 redirect).

Cap: 200 jobs, max 10 pages.
"""
from __future__ import annotations

import asyncio

import httpx
from bs4 import BeautifulSoup

from src.models.job import Job
from src.scrapers.base import BaseScraper, USER_AGENT, REQUEST_DELAY

BASE = "https://jobs.politik-kommunikation.de"
LISTING_PATH = "/stellen-beruf/bundestag-ministerien-verwaltung"
MAX_PAGES = 10
JOB_CAP = 200


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        jobs: list[Job] = []
        seen_urls: set[str] = set()

        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            for page_num in range(1, MAX_PAGES + 1):
                url = (
                    f"{BASE}{LISTING_PATH}"
                    if page_num == 1
                    else f"{BASE}{LISTING_PATH}?page={page_num}"
                )
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    await asyncio.sleep(REQUEST_DELAY)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in (400, 404) and page_num > 1:
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
                page_jobs = self._parse_page(soup, seen_urls)

                if not page_jobs:
                    break

                jobs.extend(page_jobs)
                self.log.debug(f"Page {page_num}: {len(page_jobs)} jobs")

                if len(jobs) >= JOB_CAP:
                    break

        self.log.info(f"Total: {len(jobs)} jobs")
        return jobs[:JOB_CAP]

    def _parse_page(self, soup: BeautifulSoup, seen_urls: set[str]) -> list[Job]:
        jobs: list[Job] = []

        for card in soup.select("a.job-listing"):
            href = card.get("href", "").strip()
            if not href:
                continue
            url = href if href.startswith("http") else f"{BASE}{href}"
            if url in seen_urls:
                continue
            seen_urls.add(url)

            title_el = card.select_one("h3.job-listing__title")
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                continue

            org_el = card.select_one("span.job-listing__company")
            org = org_el.get_text(strip=True) if org_el else self.name

            loc_el = card.select_one("span.location")
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
                )
            )

        return jobs
