from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup
from readability import Document

from src.models.job import Job

log = logging.getLogger(__name__)

USER_AGENT = "Pol-Intel/1.0 (contact@orison.co)"

# Phrases that indicate a captcha or access-control page rather than job content.
# If the extracted text starts with any of these, treat the fetch as failed.
_CHALLENGE_PHRASES = (
    "quick check needed",
    "javascript is required",
    "please enable javascript",
    "access denied",
    "403 forbidden",
    "captcha",
    "are you a robot",
    "verify you are human",
    "checking your browser",
)

_JSON_LD_RE = re.compile(
    r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def _looks_like_challenge(text: str) -> bool:
    lower = text.lower()[:200]
    return any(phrase in lower for phrase in _CHALLENGE_PHRASES)


def _parse_job_ld(html: str) -> dict:
    """Extract hiringOrganization, jobLocation, and validThrough from a
    JobPosting JSON-LD block.  Returns a dict with keys 'organisation',
    'location', 'closing_date' — any of which may be None.
    """
    for raw in _JSON_LD_RE.findall(html):
        try:
            data = json.loads(raw.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict) or data.get("@type") != "JobPosting":
            continue

        # Organisation
        org: str | None = None
        hiring = data.get("hiringOrganization")
        if isinstance(hiring, dict):
            org = (hiring.get("name") or "").strip() or None

        # Location — prefer addressLocality, fall back to addressRegion
        location: str | None = None
        job_loc = data.get("jobLocation")
        if isinstance(job_loc, list):
            job_loc = job_loc[0] if job_loc else None
        if isinstance(job_loc, dict):
            address = job_loc.get("address", {})
            if isinstance(address, dict):
                parts = [
                    address.get("addressLocality"),
                    address.get("addressRegion"),
                ]
                location = ", ".join(p for p in parts if p) or None

        # Closing date from validThrough ISO string
        closing_date: str | None = None
        valid_through = data.get("validThrough") or ""
        if valid_through:
            try:
                closing_date = str(valid_through)[:10]  # "2026-07-17T..." → "2026-07-17"
            except Exception:
                pass

        return {"organisation": org, "location": location, "closing_date": closing_date}

    return {"organisation": None, "location": None, "closing_date": None}


async def _fetch_html(url: str) -> str | None:
    """Fetch raw HTML for a job page.  Returns None on any error."""
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=15.0,
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                log.warning(f"enrich: HTTP {resp.status_code} for {url}")
                return None
        return resp.text
    except Exception as exc:
        log.warning(f"enrich: fetch failed for {url}: {exc}")
        return None


def _description_from_html(html: str) -> str | None:
    """Extract main readable text from HTML via readability.  Returns None if
    extraction produces less than 50 characters or looks like a challenge page."""
    try:
        doc = Document(html)
        summary_html = doc.summary()
        soup = BeautifulSoup(summary_html, "lxml")
        text = soup.get_text(separator=" ", strip=True)
        text = " ".join(text.split())
        if len(text) < 50 or _looks_like_challenge(text):
            return None
        return text[:5000]
    except Exception:
        return None


async def enrich_description(url: str, existing_description: str = None) -> Optional[str]:
    """Fetches the job page and extracts the main content body.
    Returns the extracted text, or None if extraction fails.
    Does NOT enrich if existing_description is already substantive (>200 chars)."""
    if existing_description and len(existing_description.strip()) > 200:
        return existing_description

    html = await _fetch_html(url)
    if not html:
        return None
    return _description_from_html(html)


async def enrich_jobs(
    jobs: List[Job],
    concurrency: int = 3,
    delay: float = 1.5,
) -> List[Job]:
    """Enriches descriptions for jobs that need it, with concurrency limits and
    polite delays.

    For each job with a short (<200 char) description the function:
      1. Fetches the job page once.
      2. Extracts the main readable text via readability → updates description.
      3. Parses any JobPosting JSON-LD on the same page:
           - Sets organisation if the current value is a source-name placeholder.
           - Sets location if currently None.
           - Sets closing_date if currently None.
    """
    sem = asyncio.Semaphore(concurrency)

    async def _enrich_one(job: Job) -> None:
        async with sem:
            if not job.url:
                return

            html = await _fetch_html(job.url)
            if not html:
                await asyncio.sleep(delay)
                return

            # Description
            desc = _description_from_html(html)
            if desc:
                job.description = desc

            # Structured metadata from JSON-LD (no extra HTTP request)
            meta = _parse_job_ld(html)

            # Organisation: only overwrite when the current value is the
            # source-name placeholder set by scrapers that cannot derive
            # the real employer (e.g. Political Job Hunt sitemap approach).
            if meta["organisation"] and job.organisation == job.source_name:
                job.organisation = meta["organisation"]

            # Location and closing date: fill gaps only
            if meta["location"] and not job.location:
                job.location = meta["location"]
            if meta["closing_date"] and not job.closing_date:
                job.closing_date = meta["closing_date"]

            await asyncio.sleep(delay)

    jobs_to_enrich = [
        j for j in jobs
        if not j.description or len(j.description.strip()) < 200
    ]

    if not jobs_to_enrich:
        log.info("readability enricher: no jobs need enrichment")
        return jobs

    log.info(f"readability enricher: enriching {len(jobs_to_enrich)} jobs")
    await asyncio.gather(*[_enrich_one(j) for j in jobs_to_enrich])
    return jobs
