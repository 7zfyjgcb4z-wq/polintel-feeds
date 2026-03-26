"""
CharityJob scraper.

No JS rendering. Pagination via ?page=N.
Job cards: article[job-id].job-card-wrapper
Organisation and location combined in .organisation div.
"""
from __future__ import annotations

import asyncio
import re

import httpx
from bs4 import BeautifulSoup

from src.models.job import Job
from src.scrapers.base import BaseScraper, USER_AGENT, REQUEST_DELAY

BASE = "https://www.charityjob.co.uk"

SEARCH_URLS = [
    f"{BASE}/jobs?keywords=policy&sort=latest",
    f"{BASE}/jobs?keywords=public+affairs&sort=latest",
    f"{BASE}/jobs?keywords=advocacy&sort=latest",
    f"{BASE}/jobs?keywords=campaigns+manager&sort=latest",
]

MAX_PAGES = 10  # per search term


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        seen_ids: set[str] = set()
        jobs: list[Job] = []

        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            for search_url in SEARCH_URLS:
                page = 1
                while page <= MAX_PAGES:
                    url = search_url if page == 1 else f"{search_url}&page={page}"
                    try:
                        r = await client.get(url)
                        r.raise_for_status()
                        await asyncio.sleep(REQUEST_DELAY)
                    except httpx.HTTPError as e:
                        self.log.error(f"Fetch error {url}: {e}")
                        break

                    soup = BeautifulSoup(r.text, "lxml")
                    page_jobs, total_pages = self._parse_page(soup, seen_ids)

                    if not page_jobs:
                        break

                    jobs.extend(page_jobs)
                    self.log.debug(f"Page {page}/{total_pages}: {len(page_jobs)} new jobs")

                    if page >= (total_pages or 1):
                        break
                    page += 1

        self.log.info(f"Total: {len(jobs)} jobs")
        return jobs

    def _parse_page(
        self, soup: BeautifulSoup, seen_ids: set[str]
    ) -> tuple[list[Job], int]:
        jobs: list[Job] = []

        total_pages = 1
        paging = soup.select_one(".job-paging-summary, .float-left.job-paging-summary")
        if paging:
            m = re.search(r"Page \d+ of (\d+)", paging.get_text())
            if m:
                total_pages = int(m.group(1))

        for article in soup.select("article[job-id].job-card-wrapper"):
            job_id = article.get("job-id", "")
            if not job_id or job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            if article.get("is-expired-job") == "true":
                continue

            # Title
            title_el = article.select_one(".job-title span.hidden-xs, .job-title span")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title:
                continue

            # URL
            link_el = article.select_one(".job-title a")
            if link_el and link_el.get("href"):
                href = link_el["href"]
                url = href if href.startswith("http") else f"{BASE}{href}"
            else:
                url = f"{BASE}/jobs/{job_id}"
            url = re.sub(r"\?tsId=\d+", "", url)

            # Organisation + location (combined: "Org Name, Location")
            org_el = article.select_one(".organisation")
            org_raw = org_el.get_text(strip=True) if org_el else ""
            if "," in org_raw:
                parts = org_raw.rsplit(",", 1)
                org = parts[0].strip()
                location: str | None = parts[1].strip()
            else:
                org = org_raw or "CharityJob"
                location = None

            desc = f"Role at {org}" + (f" ({location})" if location else "")

            jobs.append(
                Job(
                    title=title,
                    url=url,
                    organisation=org,
                    description=desc[:500],
                    source_name=self.name,
                    category=self.category,
                    country=self.country,
                    location=location,
                    closing_date=None,
                )
            )

        return jobs, total_pages
