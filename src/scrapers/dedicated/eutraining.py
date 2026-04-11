"""
EU Training Jobs scraper.

Parses the views-table at https://eutraining.eu/eu-jobs.
Columns: contract type, position (title + org, with link), description,
reference, grade, deadline (with apply link).
"""
from __future__ import annotations

import asyncio
import re

import httpx
from bs4 import BeautifulSoup

from src.models.job import Job
from src.scrapers.base import BaseScraper, USER_AGENT, REQUEST_DELAY

BASE = "https://eutraining.eu"
JOBS_URL = f"{BASE}/eu-jobs"
MAX_JOBS = 200


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        try:
            return await self._scrape()
        except Exception as e:
            self.log.error(f"EU Training scrape failed: {e}")
            return []

    async def _scrape(self) -> list[Job]:
        jobs: list[Job] = []

        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            try:
                r = await client.get(JOBS_URL)
                r.raise_for_status()
                await asyncio.sleep(REQUEST_DELAY)
            except httpx.HTTPError as e:
                self.log.error(f"Fetch error: {e}")
                return []

            soup = BeautifulSoup(r.text, "lxml")
            table = soup.find("table", class_="views-table")
            if not table:
                self.log.warning("views-table not found on EU Training page")
                return []

            for row in table.find_all("tr")[1:]:  # skip header
                job = self._parse_row(row)
                if job:
                    jobs.append(job)
                if len(jobs) >= MAX_JOBS:
                    break

        self.log.info(f"Total: {len(jobs)} jobs")
        return jobs

    def _parse_row(self, row) -> Job | None:
        tds = row.find_all("td")
        if len(tds) < 2:
            return None

        # Column layout (from inspecting the page):
        # 0: contract type, 1: position (title+link+org), 2: description,
        # 3: reference, 4: grade, 5: deadline+apply-link
        pos_td = tds[1]

        title_link = pos_td.find("a", href=True)
        if not title_link:
            return None

        title = title_link.get_text(strip=True)
        if not title:
            return None

        href = title_link.get("href", "")
        detail_url = href if href.startswith("http") else f"{BASE}{href}"

        # Remaining text in position cell = org + location
        full_text = pos_td.get_text(separator=" ", strip=True)
        remaining = full_text.replace(title, "", 1).strip()
        if "," in remaining:
            parts = remaining.rsplit(",", 1)
            org = parts[0].strip()
            location: str | None = parts[1].strip()
        else:
            org = remaining or "EU Institution"
            location = None

        # Contract type (column 0)
        contract = tds[0].get_text(strip=True) if tds else ""

        # Deadline + apply link (column 5 if present)
        closing_date: str | None = None
        apply_url = detail_url
        if len(tds) >= 6:
            deadline_td = tds[5]
            apply_link = deadline_td.find("a", href=re.compile(r"^http"))
            if apply_link:
                apply_url = apply_link["href"]
            deadline_text = deadline_td.get_text(strip=True)
            m = re.search(r"(\d{1,2}\s+\w{3}(?:\s+\d{4})?)", deadline_text)
            if m:
                closing_date = m.group(1)

        desc_parts = []
        if location:
            desc_parts.append(f"Role at {org} in {location}.")
        else:
            desc_parts.append(f"Role at {org}.")
        if contract:
            desc_parts.append(f"Contract: {contract}.")
        if closing_date:
            desc_parts.append(f"Deadline: {closing_date}.")
        desc = " ".join(desc_parts)

        return Job(
            title=title,
            url=detail_url,
            organisation=org,
            description=desc[:500],
            source_name=self.name,
            category=self.category,
            country=self.country,
            location=location,
            closing_date=closing_date,
        )
