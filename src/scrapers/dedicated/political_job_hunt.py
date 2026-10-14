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

Each job page carries a static JobPosting JSON-LD block (the SPA shell does not
hide it).  It is read here, at ingest, for the description and the real hiring
organisation.  When a page cannot be fetched or has no usable JSON-LD, the job
is emitted with an EMPTY description and the source-name placeholder
organisation, so downstream treats it as missing rather than classifying on a
placeholder sentence.  The item URL (job identity) is never changed.
"""
from __future__ import annotations

import asyncio
import re
import time
from xml.etree import ElementTree as ET

import httpx

from bs4 import BeautifulSoup

from src.enrichment.readability_enricher import parse_job_ld
from src.models.job import Job
from src.scrapers.base import BaseScraper, USER_AGENT, REQUEST_DELAY, fetch_with_retry

BASE = "https://www.politicaljobhunt.com"
SITEMAP_URL = f"{BASE}/sitemap.xml"
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
JOB_CAP = 200

# Detail-page fetch limits.  The whole source must fit in about five minutes.
DETAIL_TIMEOUT = 15.0      # seconds per request (was 30 via _make_client)
DETAIL_RETRIES = 1         # one retry (was 3, with up to 14s of backoff each)
DETAIL_BUDGET_SECONDS = 240.0   # stop fetching and emit what we have

# Strip trailing 8-char hex job-ID suffix from URL slugs
_ID_RE = re.compile(r"-[0-9a-f]{8}$")


def _slug_to_title(slug: str) -> str:
    """Convert a URL slug to a human-readable job title.

    'government-affairs-manager-ab12cd34' → 'Government Affairs Manager'
    """
    clean = _ID_RE.sub("", slug)
    return " ".join(w.capitalize() for w in clean.split("-"))


# The sitemap-only placeholder this scraper used to emit as a description.
# Kept so downstream code and tests can recognise rows written before this change.
LEGACY_STUB_DESCRIPTION = "Policy and political role. See link for full details."

MIN_DESCRIPTION_CHARS = 50
MAX_DESCRIPTION_CHARS = 10000


def _ld_description_to_text(raw: str) -> str:
    """Convert a JSON-LD description (HTML or plain text) to plain text."""
    text = BeautifulSoup(raw, "lxml").get_text(separator="\n")
    lines = (line.strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)[:MAX_DESCRIPTION_CHARS]


def apply_job_ld(job: Job, ld: dict) -> bool:
    """Fill description and organisation on ``job`` from parsed JSON-LD.

    Returns True when a usable description was found.  Organisation is only
    replaced while it is still the source-name placeholder.
    """
    if ld.get("organisation") and job.organisation == job.source_name:
        job.organisation = ld["organisation"]
    if ld.get("location") and not job.location:
        job.location = ld["location"]
    if ld.get("closing_date") and not job.closing_date:
        job.closing_date = ld["closing_date"]
    raw = ld.get("description")
    if not raw:
        return False
    text = _ld_description_to_text(raw)
    if len(text) < MIN_DESCRIPTION_CHARS:
        return False
    job.description = text
    job.description_source = "structured"
    return True


class Scraper(BaseScraper):
    # Set by the pipeline to the URLs already stored; empty means "fetch all".
    known_urls: set[str] | frozenset[str] = frozenset()

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
                    description="",
                    source_name=self.name,
                    category=self.category,
                    country=self.country,
                    partisan_lean=partisan_lean,
                )
            )

            if len(jobs) >= JOB_CAP:
                break

        self.log.info(f"Total: {len(jobs)} jobs from sitemap")
        await self._read_job_ld(jobs)
        return jobs

    async def _read_job_ld(self, jobs: list[Job]) -> None:
        """Fetch each NEW job page once and read its JobPosting JSON-LD.

        Jobs whose URL is already in ``known_urls`` are skipped (the feeds
        contract is one polite fetch per new job).  Fetching stops when the
        time budget is spent; remaining jobs are emitted with an empty
        description and picked up on a later run.  The REQUEST_DELAY gap
        between fetches to the host is kept.
        """
        todo = [j for j in jobs if j.url not in self.known_urls]
        filled = attempted = 0
        start = time.monotonic()
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=DETAIL_TIMEOUT,
        ) as client:
            for job in todo:
                if time.monotonic() - start >= DETAIL_BUDGET_SECONDS:
                    self.log.warning(
                        f"Detail-page budget of {DETAIL_BUDGET_SECONDS:.0f}s spent; "
                        f"{len(todo) - attempted} jobs left without a fetch"
                    )
                    break
                attempted += 1
                try:
                    r = await fetch_with_retry(client, job.url, retries=DETAIL_RETRIES)
                    ld = parse_job_ld(r.text)
                except Exception as exc:  # noqa: BLE001 - one bad page must not sink the run
                    self.log.warning(f"JSON-LD read failed for {job.url}: {type(exc).__name__}: {exc}")
                else:
                    if apply_job_ld(job, ld):
                        filled += 1
                await asyncio.sleep(REQUEST_DELAY)
        self.log.info(
            f"JSON-LD description read for {filled}/{attempted} fetched "
            f"({len(jobs) - len(todo)} known skipped, {len(todo) - attempted} unfetched)"
        )
