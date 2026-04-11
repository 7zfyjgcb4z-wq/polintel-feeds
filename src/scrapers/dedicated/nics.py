"""
Northern Ireland Civil Service (NICS) iRecruit scraper.

ASP.NET WebForms, fully server-rendered. Single page (~20 jobs).
URL: https://irecruit-ext.hrconnect.nigov.net/jobs/vacancies.aspx
"""
from __future__ import annotations

import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from src.models.job import Job
from src.scrapers.base import BaseScraper, USER_AGENT

VACANCIES_URL = "https://irecruit-ext.hrconnect.nigov.net/jobs/vacancies.aspx"
BASE = "https://irecruit-ext.hrconnect.nigov.net"


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            r = await client.get(VACANCIES_URL)
            r.raise_for_status()

        soup = BeautifulSoup(r.text, "lxml")
        jobs = self._parse_jobs(soup)
        self.log.info(f"Total: {len(jobs)} jobs")
        return jobs

    def _parse_jobs(self, soup: BeautifulSoup) -> list[Job]:
        jobs: list[Job] = []

        for div in soup.select("div.jobs-story"):
            link_el = div.select_one("h2 a")
            if not link_el:
                continue

            raw_title = link_el.get_text(strip=True)
            href = link_el.get("href", "")
            url = href if href.startswith("http") else f"{BASE}{href}"

            # Strip IRC reference prefix from title
            title = re.sub(r"^IRC\d+\s*[-–]\s*", "", raw_title).strip()

            dept = self._field(div, "DEPARTMENT")
            salary = self._field(div, "SALARY")
            location = self._field(div, "LOCATION")

            close_el = div.select_one("span.jobs-date")
            closing = None
            if close_el:
                closing = self._parse_date(close_el.get_text(strip=True))

            org = dept or "Northern Ireland Civil Service"
            desc_parts = []
            if location:
                desc_parts.append(f"Role at {org} in {location}.")
            else:
                desc_parts.append(f"Role at {org}.")
            if salary:
                desc_parts.append(f"Salary: {salary}.")
            if closing:
                desc_parts.append(f"Closing: {closing}.")
            desc = " ".join(desc_parts)

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
                    closing_date=closing,
                )
            )
        return jobs

    @staticmethod
    def _field(div: BeautifulSoup, label: str) -> str | None:
        """Extract value from <p><strong>LABEL: </strong>value</p>."""
        strong = div.find("strong", string=re.compile(label, re.I))
        if strong:
            text = strong.parent.get_text(strip=True)
            text = re.sub(rf"^{label}\s*:\s*", "", text, flags=re.I).strip()
            return text or None
        return None

    @staticmethod
    def _parse_date(text: str) -> str | None:
        """Parse 'Closing Date: Tuesday 14 April 2026'."""
        match = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", text)
        if match:
            try:
                day, month, year = match.groups()
                return datetime.strptime(f"{day} {month} {year}", "%d %B %Y").strftime("%Y-%m-%d")
            except ValueError:
                pass
        return None
