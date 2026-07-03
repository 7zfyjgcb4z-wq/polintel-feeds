"""
EuroBrussels scraper.

Uses the /api/live_search JSON endpoint. Jobs are returned as:
  {"description": "Job Title", "url_ending": "/job_display/{id}/{slug}", "type": "job"}

We query with ~20 broad EU-affairs keywords to capture the full listing and
dedup by job ID. Organisation, location and dates come from the detail page
via the enricher's org_from_page cascade (Stage 3), not from the URL slug.
"""
from __future__ import annotations

import asyncio
import re

import httpx

from src.models.job import Job
from src.scrapers.base import BaseScraper, USER_AGENT, REQUEST_DELAY

BASE = "https://www.eurobrussels.com"
API = f"{BASE}/api/live_search"
MAX_JOBS = 200

# Broad queries that together cover almost all EU-affairs postings
QUERIES = [
    "policy", "eu", "european", "affairs", "commission", "parliament",
    "council", "advocacy", "research", "communications", "legal",
    "governance", "intern", "traineeship", "analyst", "officer",
    "advisor", "manager", "coordinator", "director",
]


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        try:
            return await self._scrape()
        except Exception as e:
            self.log.error(f"EuroBrussels scrape failed: {e}")
            return []

    async def _scrape(self) -> list[Job]:
        seen_ids: set[str] = set()
        jobs: list[Job] = []

        async with httpx.AsyncClient(
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            },
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            for query in QUERIES:
                if len(jobs) >= MAX_JOBS:
                    break
                try:
                    r = await client.get(API, params={"p_live_search_input": query})
                    r.raise_for_status()
                    await asyncio.sleep(REQUEST_DELAY)
                except httpx.HTTPError as e:
                    self.log.warning(f"API error for query '{query}': {e}")
                    continue

                try:
                    items = r.json()
                except Exception:
                    continue

                for item in items:
                    if item.get("type") != "job":
                        continue
                    url_ending = item.get("url_ending", "")
                    if not url_ending:
                        continue

                    # Extract numeric job ID from path like /job_display/289254/slug
                    m = re.search(r"/job_display/(\d+)/", url_ending)
                    if not m:
                        continue
                    job_id = m.group(1)
                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    title = item.get("description", "").strip()
                    if not title or title.startswith("---"):
                        continue

                    url = f"{BASE}{url_ending}"

                    jobs.append(
                        Job(
                            title=title,
                            url=url,
                            organisation=self.name,   # placeholder; enricher fills from the detail page
                            description="",            # empty -> 'none' -> enrichment triggers
                            source_name=self.name,
                            category=self.category,
                            country=self.country,
                            location=None,
                        )
                    )

                    if len(jobs) >= MAX_JOBS:
                        break

        self.log.info(f"Total: {len(jobs)} jobs")
        return jobs
