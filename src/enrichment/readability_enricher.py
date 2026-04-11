from __future__ import annotations

import asyncio
import logging
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


def _looks_like_challenge(text: str) -> bool:
    lower = text.lower()[:200]
    return any(phrase in lower for phrase in _CHALLENGE_PHRASES)


async def enrich_description(url: str, existing_description: str = None) -> Optional[str]:
    """Fetches the job page and extracts the main content body.
    Returns the extracted text, or None if extraction fails.
    Does NOT enrich if existing_description is already substantive (>200 chars)."""
    if existing_description and len(existing_description.strip()) > 200:
        return existing_description

    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=15.0,
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                log.warning(f"enrich_description: HTTP {resp.status_code} for {url}")
                return None

        doc = Document(resp.text)
        summary_html = doc.summary()
        soup = BeautifulSoup(summary_html, "lxml")
        text = soup.get_text(separator=" ", strip=True)
        text = " ".join(text.split())

        if len(text) < 50:
            return None

        if _looks_like_challenge(text):
            log.debug(f"enrich_description: challenge/captcha page detected for {url} — skipping")
            return None

        return text[:5000]

    except Exception as e:
        log.warning(f"enrich_description failed for {url}: {e}")
        return None


async def enrich_jobs(
    jobs: List[Job],
    concurrency: int = 3,
    delay: float = 1.5,
) -> List[Job]:
    """Enriches descriptions for jobs that need it, with concurrency limits and polite delays."""
    sem = asyncio.Semaphore(concurrency)

    async def _enrich_one(job: Job) -> None:
        async with sem:
            if not job.url:
                return
            desc = await enrich_description(job.url, job.description)
            if desc:
                job.description = desc
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
