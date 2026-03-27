"""
LGA (Local Government Association) Jobs scraper.

Portal: https://www.careers.local.gov.uk/jobs
Ruby on Rails, fully server-rendered. Small board (~5-20 jobs).
Closing date from JSON-LD on each detail page.
"""
from __future__ import annotations

import asyncio
import json
import re

import httpx
from bs4 import BeautifulSoup

from src.models.job import Job
from src.scrapers.base import BaseScraper, USER_AGENT, REQUEST_DELAY

BASE = "https://www.careers.local.gov.uk"
JOBS_URL = f"{BASE}/jobs"


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            r = await client.get(JOBS_URL)
            r.raise_for_status()
            await asyncio.sleep(REQUEST_DELAY)

            soup = BeautifulSoup(r.text, "lxml")
            stubs = self._parse_stubs(soup)

            jobs: list[Job] = []
            for stub in stubs:
                closing = await self._get_closing_date(client, stub["url"])
                desc_parts = ["Local Government Association"]
                if stub.get("location"):
                    desc_parts.append(stub["location"])
                if stub.get("salary"):
                    desc_parts.append(f"Salary: {stub['salary']}")
                if closing:
                    desc_parts.append(f"Closes: {closing}")
                jobs.append(
                    Job(
                        title=stub["title"],
                        url=stub["url"],
                        organisation="Local Government Association",
                        description=" | ".join(desc_parts)[:500],
                        source_name=self.name,
                        category=self.category,
                        country=self.country,
                        location=stub.get("location"),
                        closing_date=closing,
                    )
                )

        self.log.info(f"Total: {len(jobs)} jobs")
        return jobs

    def _parse_stubs(self, soup: BeautifulSoup) -> list[dict]:
        stubs = []
        for li in soup.select("li.job-result-item"):
            title_el = li.select_one("div.job-title a")
            if not title_el:
                continue
            href = title_el.get("href", "")
            url = href if href.startswith("http") else f"{BASE}{href}"
            title = title_el.get_text(strip=True)

            loc_el = li.select_one("li.results-job-location")
            location = loc_el.get_text(strip=True) if loc_el else None

            salary_el = li.select_one("li.results-salary")
            salary = salary_el.get_text(strip=True) if salary_el else ""

            stubs.append({"title": title, "url": url, "location": location, "salary": salary})
        return stubs

    async def _get_closing_date(self, client: httpx.AsyncClient, url: str) -> str | None:
        try:
            r = await client.get(url)
            r.raise_for_status()
            await asyncio.sleep(REQUEST_DELAY)
            soup = BeautifulSoup(r.text, "lxml")

            # JSON-LD validThrough
            ld_script = soup.find("script", type="application/ld+json")
            if ld_script:
                ld = json.loads(ld_script.string or "{}")
                valid_through = ld.get("validThrough")
                if valid_through:
                    return valid_through[:10]
        except Exception as e:
            self.log.debug(f"Could not get closing date for {url}: {e}")
        return None
