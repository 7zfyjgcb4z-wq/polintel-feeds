from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup
from readability import Document

from src.enrichment.labelled_fields import parse_labelled_fields
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

# Page-level fingerprints. DEAD means the posting no longer exists: the job is
# dropped from the run entirely (emitting it would re-advertise a dead role).
# UNREADABLE means the page cannot be read without JS or is access-blocked:
# the body is refused and the job keeps its existing description (possibly
# empty, labelled 'none'), which scores 0 at ingestion and is quarantined.
# Matched case-insensitively as substrings of the RAW page HTML.
DEAD_PAGE_SIGNATURES = (
    "we're sorry, the job you are looking for",   # EuroBrussels expired-job page, verified live 2026-07-02
    "we're sorry, that job does not exist",       # confirmed E3 2026-07-03: German Marshall Fund via
                                                   # Paylocity expired-job page ("We're sorry, that job
                                                   # does not exist or is not currently active."),
                                                   # recruiting.paylocity.com
)
UNREADABLE_PAGE_SIGNATURES = (
    "in order to use this site, it is necessary to enable javascript",  # Paylocity JS wall, verified live 2026-07-02
)

# Stored descriptions matching one of these prefixes are treated as degraded
# and re-enriched even if they are 200+ chars. Kept in sync with the
# canonical tuple in src/pipeline.py (Stage 3 spec section 7).
DEGRADED_PREFIXES = (
    "To provide the best experiences, we use technologies like cookies",
    "We're sorry, that job does not exist",
    "What do you think of this job?",
)

_JSON_LD_RE = re.compile(
    r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def _needs_enrichment(desc: str | None) -> bool:
    t = (desc or "").strip()
    if len(t) < 200:
        return True
    return any(t.startswith(p) for p in DEGRADED_PREFIXES)


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
        # Strip Complianz cookie consent elements before readability runs.
        # On WordPress sites with fragmented layouts (e.g. pac.org), the
        # Complianz banner div contains more continuous text than any
        # individual content div, so readability incorrectly identifies it
        # as the main content. Stripping it first forces readability to
        # score real content.
        pre_soup = BeautifulSoup(html, "lxml")
        for el in pre_soup.select(
            '[class^="cmplz-"], [class*=" cmplz-"], [id^="cmplz-"]'
        ):
            el.decompose()

        # Text-anchored strip for consent dialogues regardless of CSS classes.
        # Verified live 2026-07-02 on pac.org and greenparty.org.uk: both banners
        # begin with this exact sentence (behaviour/behavior spelling diverges later).
        _CONSENT_ANCHOR = "To provide the best experiences, we use technologies like cookies"
        for text_node in pre_soup.find_all(string=lambda s: s and s.strip().startswith(_CONSENT_ANCHOR)):
            container = text_node
            # climb to the outermost element that still starts with the anchor
            while (container.parent is not None
                   and container.parent.name not in ("body", "html", "[document]")
                   and container.parent.get_text(strip=True).startswith(_CONSENT_ANCHOR)):
                container = container.parent
            el = container if hasattr(container, "decompose") else container.parent
            if el is not None and hasattr(el, "decompose"):
                el.decompose()

        html = str(pre_soup)

        doc = Document(html)
        summary_html = doc.summary()
        soup = BeautifulSoup(summary_html, "lxml")
        text = soup.get_text(separator="\n", strip=True)
        text = "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip())
        if len(text) < 50 or _looks_like_challenge(text):
            return None
        return text[:10000]
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
    source_configs: dict[str, dict] | None = None,
) -> List[Job]:
    """Enriches descriptions for jobs that need it, with concurrency limits and
    polite delays.

    For each job whose description is missing, short, or matches a degraded
    fingerprint, the function:
      1. Fetches the job page once.
      2. Drops the job entirely if the page matches a dead-page fingerprint.
      3. Refuses the body (fail loud) if the page matches an unreadable-page
         fingerprint.
      4. Extracts the main body via a per-source content_scope selector if
         configured, else via readability.
      5. Parses per-source labelled fields (organisation/location/dates) from
         the extracted text.
      6. Parses any JobPosting JSON-LD on the same page as a gap-filler.
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

            lower_html = html.lower()
            if any(sig in lower_html for sig in DEAD_PAGE_SIGNATURES):
                job._dead_page = True  # pipeline drops this job before storage
                await asyncio.sleep(delay)
                return
            if any(sig in lower_html for sig in UNREADABLE_PAGE_SIGNATURES):
                # Fail loud: refuse the body. Do NOT extract, do NOT fall through
                # to readability (it would capture the JS-wall text as the body).
                await asyncio.sleep(delay)
                return

            cfg = (source_configs or {}).get(job.source_name, {})
            scope_sel = cfg.get("content_scope")
            desc = None
            if scope_sel:
                scoped = BeautifulSoup(html, "lxml").select_one(scope_sel)
                if scoped is not None:
                    text = scoped.get_text(separator="\n", strip=True)
                    text = "\n".join(line for line in (l.strip() for l in text.splitlines()) if line)
                    if len(text) >= 50 and not _looks_like_challenge(text):
                        desc = text[:10000]
            if desc is None:
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

            # Per-source labelled-field extraction (deterministic 'Label: value' parsing)
            labelled = parse_labelled_fields(desc or "", cfg.get("labelled_fields") or {})
            if labelled.get("organisation") and job.organisation in (job.source_name, "", None):
                job.organisation = labelled["organisation"]
            if labelled.get("location") and not job.location:
                job.location = labelled["location"]
            if labelled.get("posted_date") and not job.posted_date:
                job.posted_date = labelled["posted_date"]
            if labelled.get("closing_date") and not job.closing_date:
                job.closing_date = labelled["closing_date"]
            if desc and labelled:
                job.description_source = "structured"
            elif desc:
                job.description_source = "readability"

            # EuroBrussels detail pages carry the decoded employer name on the
            # jobs_at anchor (verified live 2026-07-02: <a href=".../jobs_at/{slug}/{id}">
            # with an <img title="EUROPEX - Association of European Energy Exchanges">),
            # and og:title of the form "Job Title - Org Name, City".
            if job.organisation == job.source_name and cfg.get("org_from_page"):
                page = BeautifulSoup(html, "lxml")
                anchor = page.select_one('a[href*="/jobs_at/"]')
                org_val = None
                if anchor is not None:
                    img = anchor.find("img")
                    org_val = (img.get("title") if img else None) or anchor.get_text(strip=True) or None
                if not org_val:
                    og = page.select_one('meta[property="og:title"]')
                    if og and og.get("content"):
                        rest = og["content"]
                        if rest.startswith(job.title):
                            rest = rest[len(job.title):].lstrip(" -")
                        if "," in rest:
                            org_val, _, loc_part = rest.rpartition(",")
                            if not job.location and loc_part.strip():
                                job.location = loc_part.strip()
                        org_val = (org_val or "").strip() or None
                if org_val:
                    job.organisation = org_val
                if not job.location:
                    og = page.select_one('meta[property="og:title"]')
                    if og and og.get("content") and "," in og["content"]:
                        job.location = og["content"].rpartition(",")[2].strip() or None

                page_text = page.get_text(" ", strip=True)
                if not job.posted_date:
                    m = re.search(r"Posted (?:today|(\d+) days? ago)", page_text)
                    if m:
                        days = int(m.group(1)) if m.group(1) else 0
                        job.posted_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
                if not job.closing_date:
                    m = re.search(r"Deadline (\d{1,2} [A-Z][a-z]+)", page_text)
                    if m:
                        for year in (datetime.now(timezone.utc).year, datetime.now(timezone.utc).year + 1):
                            try:
                                d = datetime.strptime(f"{m.group(1)} {year}", "%d %B %Y")
                                if d.date() >= datetime.now(timezone.utc).date():
                                    job.closing_date = d.strftime("%Y-%m-%d")
                                    break
                            except ValueError:
                                continue

            await asyncio.sleep(delay)

    jobs_to_enrich = [j for j in jobs if _needs_enrichment(j.description)]

    if not jobs_to_enrich:
        log.info("readability enricher: no jobs need enrichment")
        return jobs

    log.info(f"readability enricher: enriching {len(jobs_to_enrich)} jobs")
    await asyncio.gather(*[_enrich_one(j) for j in jobs_to_enrich])
    return jobs
