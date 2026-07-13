"""
jobs.ac.uk scraper — Politics & Government and Environmental Sciences disciplines.

Server-rendered HTML, no JS required. No RSS feed available.
Pagination: ?startIndex=N (increments of 25).
Each discipline facet gets its own pagination budget; results are deduped by URL.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

from src.models.job import Job
from src.scrapers.base import BaseScraper, USER_AGENT, REQUEST_DELAY

BASE = "https://www.jobs.ac.uk"

# International relations roles appear under politics-and-government on jobs.ac.uk
# (no dedicated international-relations facet exists in their taxonomy, verified 2026-07-13).
DISCIPLINE_FACETS = [
    "politics-and-government",
    "environmental-sciences",  # sustainability/environment roles
]

BASE_PARAMS = {
    "activeFacet": "academicDisciplineFacet",
    "sortOrder": "1",
    "pageSize": "25",
}
MAX_PAGES = 20  # per-facet cap: 20 × 25 = 500 jobs max per discipline

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        all_jobs: list[Job] = []

        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            for facet in DISCIPLINE_FACETS:
                start_index = 1
                page = 0

                while page < MAX_PAGES:
                    params = {
                        **BASE_PARAMS,
                        "academicDisciplineFacet[0]": facet,
                        "startIndex": str(start_index),
                    }
                    url = f"{BASE}/search/?{urlencode(params)}"

                    try:
                        r = await client.get(url)
                        r.raise_for_status()
                        await asyncio.sleep(REQUEST_DELAY)
                    except httpx.HTTPError as e:
                        self.log.error(f"Page error at facet={facet} startIndex={start_index}: {e}")
                        break

                    soup = BeautifulSoup(r.text, "lxml")
                    page_jobs = self._parse_jobs(soup)
                    all_jobs.extend(page_jobs)
                    page += 1
                    self.log.debug(f"facet={facet} startIndex={start_index}: {len(page_jobs)} jobs")

                    if len(page_jobs) < 25:
                        break
                    start_index += 25

        seen: set[str] = set()
        deduped: list[Job] = []
        for job in all_jobs:
            if job.url in seen:
                continue
            seen.add(job.url)
            deduped.append(job)

        self.log.info(f"Total: {len(deduped)} jobs across {len(DISCIPLINE_FACETS)} facets")
        return deduped

    def _parse_jobs(self, soup: BeautifulSoup) -> list[Job]:
        jobs: list[Job] = []

        for div in soup.select("div.j-search-result__result"):
            link_el = div.select_one("div.j-search-result__text > a")
            if not link_el:
                continue
            title = link_el.get_text(strip=True)
            href = link_el.get("href", "")
            url = href if href.startswith("http") else f"{BASE}{href}"

            emp_el = div.select_one(".j-search-result__employer b")
            org = emp_el.get_text(strip=True) if emp_el else "jobs.ac.uk"

            dept_el = div.select_one(".j-search-result__department")
            dept = dept_el.get_text(strip=True) if dept_el else ""

            location = None
            for el in div.select("div.j-search-result__text > div"):
                text = el.get_text(strip=True)
                if text.startswith("Location:"):
                    location = text.replace("Location:", "").strip()
                    break

            salary_el = div.select_one(".j-search-result__info")
            salary = salary_el.get_text(strip=True) if salary_el else ""

            close_el = div.select_one(".j-search-result__date--blue")
            closing = self._parse_date(close_el.get_text(strip=True)) if close_el else None

            desc_parts = [org]
            if dept:
                desc_parts.append(dept)
            if location:
                desc_parts.append(location)
            if salary:
                desc_parts.append(f"Salary: {salary}")
            if closing:
                desc_parts.append(f"Closes: {closing}")
            desc = " | ".join(desc_parts)

            jobs.append(
                Job(
                    title=title,
                    url=url,
                    organisation=org,
                    description=desc,
                    source_name=self.name,
                    category=self.category,
                    country=self.country,
                    location=location,
                    closing_date=closing,
                )
            )
        return jobs

    @staticmethod
    def _parse_date(text: str) -> str | None:
        """Parse '23 Apr' or '23 Apr 2026'."""
        m = re.match(r"(\d{1,2})\s+(\w{3,})\s*(\d{4})?", text.strip())
        if m:
            day = int(m.group(1))
            month_str = m.group(2)[:3].lower()
            year_str = m.group(3)
            month = MONTHS.get(month_str)
            if month:
                year = int(year_str) if year_str else datetime.utcnow().year
                try:
                    return datetime(year, month, day).strftime("%Y-%m-%d")
                except ValueError:
                    pass
        return None
