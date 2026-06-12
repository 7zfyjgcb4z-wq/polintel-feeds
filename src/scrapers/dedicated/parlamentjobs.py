"""
Parlamentjobs.de scraper.

WP Job Manager listing at parlamentjobs.de — aggregates party, fraction, and
political roles across German politics.  Jobs render server-side via standard
WP Job Manager markup (li.job_listing cards).  Pagination via /page/N/.

Cap: 200 jobs, max 10 pages.
"""
from __future__ import annotations

import asyncio

import httpx
from bs4 import BeautifulSoup

from src.models.job import Job
from src.scrapers.base import BaseScraper, USER_AGENT, REQUEST_DELAY

BASE = "https://parlamentjobs.de"
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
                url = f"{BASE}/" if page_num == 1 else f"{BASE}/page/{page_num}/"
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

        for card in soup.select("li.job_listing"):
            a = card.select_one("a[href]")
            if not a:
                continue
            url = a.get("href", "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            # WP Job Manager: title inside .position p strong
            title_el = card.select_one(".position strong")
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                continue

            org_el = card.select_one(".company strong")
            org = org_el.get_text(strip=True) if org_el else self.name

            loc_el = card.select_one(".location")
            location = loc_el.get_text(strip=True) if loc_el else None

            date_el = card.select_one("time[datetime]")
            posted_date = date_el.get("datetime") if date_el else None

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
                    posted_date=posted_date,
                )
            )

        return jobs
