"""
Political Job Hunt scraper (politicaljobhunt.com).

Political Wire's dedicated job board, powered by Jobboardly (JS-rendered SPA).
The listing page renders jobs entirely via JavaScript so static HTML scraping
doesn't work.  The XML sitemap at /sitemap.xml lists every active job URL with
a canonical slug, which we use to build Job objects without individual page
fetches.

Slug format:  <title-words-hyphenated>-<8-char-hex-id>
Example:      government-affairs-manager-ab12cd34 → "Government Affairs Manager"

Cap: 200 jobs per run.  The DB upsert handles deduplication on subsequent runs.
"""
from __future__ import annotations

import asyncio
import re
from xml.etree import ElementTree as ET

import httpx

from src.models.job import Job
from src.scrapers.base import BaseScraper, USER_AGENT, REQUEST_DELAY

BASE = "https://www.politicaljobhunt.com"
SITEMAP_URL = f"{BASE}/sitemap.xml"
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
JOB_CAP = 200

# Strip trailing 8-char hex job-ID suffix from URL slugs
_ID_RE = re.compile(r"-[0-9a-f]{8}$")


def _slug_to_title(slug: str) -> str:
    """Convert a URL slug to a human-readable job title.

    'government-affairs-manager-ab12cd34' → 'Government Affairs Manager'
    """
    clean = _ID_RE.sub("", slug)
    return " ".join(w.capitalize() for w in clean.split("-"))


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        partisan_lean = self.source.get("partisan_lean")

        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            try:
                r = await client.get(SITEMAP_URL)
                r.raise_for_status()
            except httpx.HTTPError as exc:
                self.log.error(f"Sitemap fetch failed: {exc}")
                return []
            await asyncio.sleep(REQUEST_DELAY)

        try:
            root = ET.fromstring(r.text)
        except ET.ParseError as exc:
            self.log.error(f"Sitemap parse error: {exc}")
            return []

        tag_loc = f"{{{SITEMAP_NS}}}loc"
        tag_url = f"{{{SITEMAP_NS}}}url"

        jobs: list[Job] = []
        for url_el in root.iter(tag_url):
            loc_el = url_el.find(tag_loc)
            if loc_el is None or not loc_el.text:
                continue

            job_url = loc_el.text.strip()
            if "/jobs/" not in job_url:
                continue

            slug = job_url.rstrip("/").rsplit("/", 1)[-1]
            title = _slug_to_title(slug)
            if not title:
                continue

            jobs.append(
                Job(
                    title=title,
                    url=job_url,
                    organisation=self.name,
                    description="Policy and political role. See link for full details.",
                    source_name=self.name,
                    category=self.category,
                    country=self.country,
                    partisan_lean=partisan_lean,
                )
            )

            if len(jobs) >= JOB_CAP:
                break

        self.log.info(f"Total: {len(jobs)} jobs from sitemap")
        return jobs
