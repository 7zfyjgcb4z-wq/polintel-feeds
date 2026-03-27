"""
myjobscotland scraper.

Uses the public JSON REST API at admin.myjobscotland.gov.uk — no HTML scraping needed.
Returns all Scottish public sector jobs (2,000+).
"""
from __future__ import annotations

import asyncio

import httpx

from src.models.job import Job
from src.scrapers.base import BaseScraper, USER_AGENT, REQUEST_DELAY

API_BASE = "https://admin.myjobscotland.gov.uk/api/v2/search"
JOB_BASE = "https://www.myjobscotland.gov.uk"
# API returns 10 items/page; adding items_per_page param breaks it.
# Cap at 100 pages (1,000 jobs) — enough coverage without 7-minute runtime.
MAX_PAGES = 100


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        jobs: list[Job] = []

        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            page = 1
            total_pages = 1

            while page <= min(total_pages, MAX_PAGES):
                params = {"_format": "json", "page": page}
                try:
                    r = await client.get(API_BASE, params=params)
                    r.raise_for_status()
                    await asyncio.sleep(1.0)  # lighter delay for a JSON API
                except httpx.HTTPError as e:
                    self.log.error(f"API error page {page}: {e}")
                    break

                data = r.json()
                total_pages = int(data.get("pages", 1))
                items = data.get("list", [])

                if not items:
                    break

                for item in items:
                    job = self._parse_item(item)
                    if job:
                        jobs.append(job)

                self.log.debug(f"Page {page}/{total_pages}: {len(items)} items")
                page += 1

        self.log.info(f"Total: {len(jobs)} jobs")
        return jobs

    def _parse_item(self, item: dict) -> Job | None:
        title = (item.get("title") or "").strip()
        relative_url = (item.get("url") or "").strip()
        if not title or not relative_url:
            return None

        url = (
            relative_url
            if relative_url.startswith("http")
            else f"{JOB_BASE}{relative_url}"
        )
        org = (item.get("org_name") or item.get("parent_org_name") or "myjobscotland").strip()
        location = (item.get("location_address_listing") or "").strip() or None
        closing_raw = (item.get("end_date") or "").strip()
        closing = closing_raw[:10] if closing_raw else None  # "YYYY-MM-DD HH:MM:SS" → "YYYY-MM-DD"

        salary = (item.get("salary_name") or "").strip()
        contract = (item.get("c_type_name") or "").strip()

        desc_parts = [org]
        if location:
            desc_parts.append(location)
        if salary:
            desc_parts.append(f"Salary: {salary}")
        if contract:
            desc_parts.append(contract)
        if closing:
            desc_parts.append(f"Closes: {closing}")
        desc = " | ".join(desc_parts)

        return Job(
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
