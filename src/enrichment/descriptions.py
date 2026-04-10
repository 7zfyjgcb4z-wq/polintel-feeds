"""
Description enrichment: fetch full job descriptions from individual listing pages.

Processes jobs that don't already have a long description (< min_existing_description_length).
Applies per-domain throttling. Failures are logged and fall back to existing metadata.
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml
from bs4 import BeautifulSoup

from src.models.job import Job

log = logging.getLogger(__name__)

# CSS selectors to try per domain (tried in order, first non-empty result wins)
DOMAIN_SELECTORS: dict[str, list[str]] = {
    "www.civilservicejobs.service.gov.uk": [
        "#job-description",
        ".job-description",
        "div[class*='description']",
    ],
    "www.charityjob.co.uk": [
        ".job-description",
        "#job-description",
        ".listing-description",
    ],
    "www.jobs.ac.uk": [
        ".job-description",
        "#enhanced-content",
        ".j-nav-content",
    ],
    "careers.local.gov.uk": [
        ".job-description",
        ".vacancy-description",
    ],
    "irecruit-ext.hrconnect.nigov.net": [
        ".job-description",
        "#job-description",
    ],
}

# Generic fallback containers (tried in order)
GENERIC_CONTAINERS = ["main", "#content", "article"]

# For Civil Service Jobs specifically: if extracted text is too short, give up
CSJ_MIN_CHARS = 200


def _extract_text(soup: BeautifulSoup, selectors: list[str]) -> str:
    """Try selectors in order; return cleaned text from the first match with content."""
    for selector in selectors:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator=" ", strip=True)
            # Collapse whitespace
            text = " ".join(text.split())
            if text:
                return text
    return ""


def _extract_generic(soup: BeautifulSoup) -> str:
    """Fall back to the largest block of paragraph text in known containers."""
    for container_sel in GENERIC_CONTAINERS:
        container = soup.select_one(container_sel)
        if container:
            paragraphs = container.find_all("p")
            if paragraphs:
                text = " ".join(p.get_text(separator=" ", strip=True) for p in paragraphs)
                text = " ".join(text.split())
                if len(text) > 100:
                    return text
            # No <p> tags — grab all text from container
            text = " ".join(container.get_text(separator=" ", strip=True).split())
            if len(text) > 100:
                return text

    # Last resort: find the largest <div> by text length
    best_text = ""
    for div in soup.find_all("div"):
        text = " ".join(div.get_text(separator=" ", strip=True).split())
        if len(text) > len(best_text):
            best_text = text
    return best_text


async def _fetch_one(
    client: httpx.AsyncClient,
    job: Job,
    max_len: int,
) -> str | None:
    """
    Fetch and extract a description from a job listing page.
    Returns the description string, or None if extraction failed or yielded too little text.
    """
    domain = urlparse(job.url).netloc
    selectors = DOMAIN_SELECTORS.get(domain)

    response = await client.get(job.url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")

    if selectors:
        text = _extract_text(soup, selectors)
        if not text:
            text = _extract_generic(soup)
    else:
        text = _extract_generic(soup)

    if not text or len(text) < 100:
        return None

    # Civil Service Jobs pages are often JS-rendered; require more content
    if domain == "www.civilservicejobs.service.gov.uk" and len(text) < CSJ_MIN_CHARS:
        return None

    return text[:max_len]


async def fetch_descriptions(
    jobs: list[Job],
    config_path: str = "src/config/exclusions.yaml",
) -> list[Job]:
    """
    Fetch full descriptions from listing pages for jobs that don't already have them.
    Updates jobs in place. Returns the same list.
    """
    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            config = yaml.safe_load(f)
        fetch_cfg = config.get("description_fetch", {})
    else:
        fetch_cfg = {}

    throttle_seconds: float = float(fetch_cfg.get("throttle_seconds", 1.5))
    timeout_seconds: float = float(fetch_cfg.get("timeout_seconds", 15))
    max_len: int = int(fetch_cfg.get("max_description_length", 5000))
    min_existing_len: int = int(fetch_cfg.get("min_existing_description_length", 500))

    # Select jobs that need a description
    jobs_to_fetch = [
        job for job in jobs
        if not job.description or len(job.description) < min_existing_len
    ]

    if not jobs_to_fetch:
        log.info("Description fetch: no jobs need enrichment")
        return jobs

    attempted = 0
    success = 0
    fallback = 0

    # Track last request time per domain for throttling
    last_request: dict[str, float] = {}

    async with httpx.AsyncClient(
        headers={"User-Agent": "Pol-Intel/1.0 (contact@orison.co)"},
        follow_redirects=True,
        timeout=timeout_seconds,
    ) as client:
        for job in jobs_to_fetch:
            domain = urlparse(job.url).netloc

            # Apply per-domain throttle
            if domain in last_request:
                elapsed = time.monotonic() - last_request[domain]
                if elapsed < throttle_seconds:
                    await asyncio.sleep(throttle_seconds - elapsed)

            attempted += 1
            try:
                desc = await _fetch_one(client, job, max_len)
                last_request[domain] = time.monotonic()

                if desc:
                    job.description = desc
                    success += 1
                else:
                    fallback += 1
            except Exception as e:
                last_request[domain] = time.monotonic()
                log.warning(f'DESC FETCH FAILED: "{job.title}" — {job.url} — {e}')
                fallback += 1

    log.info(
        f"Description fetch: {success}/{attempted} succeeded, {fallback} used metadata fallback"
    )
    return jobs
