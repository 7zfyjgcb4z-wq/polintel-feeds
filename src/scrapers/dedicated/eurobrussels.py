"""
EuroBrussels scraper.

Uses the /api/live_search JSON endpoint. Jobs are returned as:
  {"description": "Job Title", "url_ending": "/job_display/{id}/{slug}", "type": "job"}

We query with ~20 broad EU-affairs keywords to capture the full listing,
dedup by job ID, and parse org/location from the URL slug.
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

# Known country names (last word of slug) — used to extract location
_COUNTRIES = {
    "Belgium", "Germany", "France", "Netherlands", "Luxembourg", "Austria",
    "Italy", "Spain", "Sweden", "Denmark", "Finland", "Poland", "Hungary",
    "Ireland", "Portugal", "Greece", "Romania", "Bulgaria", "Croatia",
    "Czech", "Slovakia", "Slovenia", "Estonia", "Latvia", "Lithuania",
    "Cyprus", "Malta", "Switzerland", "Norway", "Turkey", "USA", "UK",
    "Countries", "Europe", "Worldwide", "Remote",
}


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
                    slug_part = url_ending.split("/", 3)[-1]  # e.g. "Senior_Policy_Adviser_..."
                    org, location = self._parse_slug(slug_part, title)

                    jobs.append(
                        Job(
                            title=title,
                            url=url,
                            organisation=org,
                            description=f"{org} | {location}"[:500],
                            source_name=self.name,
                            category=self.category,
                            country=self.country,
                            location=location,
                        )
                    )

                    if len(jobs) >= MAX_JOBS:
                        break

        self.log.info(f"Total: {len(jobs)} jobs")
        return jobs

    @staticmethod
    def _parse_slug(slug: str, title: str) -> tuple[str, str]:
        """
        Slug format: Title_Org_Name_City_Country  (underscores, no special chars)
        We strip the title portion, then split org from location at the end.
        """
        human = slug.replace("_", " ")

        # The slug encodes title words with underscores (special chars stripped).
        # Count title words and skip that many words from the slug.
        title_word_count = len(title.split())
        slug_words = human.split()
        remaining_words = slug_words[title_word_count:]  # org + location
        if not remaining_words:
            return "EuroBrussels", "Brussels"

        # Identify location: look backwards for known country/city patterns
        location_words: list[str] = []
        org_words = list(remaining_words)

        # Take up to 3 words from end as possible location
        for n in range(min(3, len(org_words)), 0, -1):
            candidate = " ".join(org_words[-n:])
            last_word = org_words[-1]
            if last_word in _COUNTRIES:
                location_words = org_words[-n:]
                org_words = org_words[:-n]
                break

        location = " ".join(location_words) if location_words else "Brussels"
        org = " ".join(org_words).strip() if org_words else "EuroBrussels"
        if not org:
            org = "EuroBrussels"

        return org, location
