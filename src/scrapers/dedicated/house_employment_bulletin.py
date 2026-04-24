"""
House Employment Bulletin scraper.

The House Vacancy Announcement and Placement Service (HVAPS) distributes a weekly
PDF bulletin of all member and committee office vacancies.  Derek Willis
(github.com/dwillis/house-jobs, MIT License) ingests each PDF and commits
structured JSON output to the repository.  This scraper consumes that public
JSON via GitHub's raw-content CDN — no PDF parsing, no HTML scraping required.

Data lag: JSON typically appears 1-2 days after the Monday/Tuesday PDF distribution.

Fetch strategy: pull the 4 most recent bulletins (~one month) on each run so that
jobs posted in prior weeks remain visible.  DB deduplication (by URL/guid) and the
30-day stale threshold in the pipeline handle the rest.

Staleness monitoring: after each run the scraper sets self.upstream_meta with the
date of the most recent bulletin.  The pipeline writes this to per-source results
and generate_alerts() emits an upstream_stale alert if the bulletin is >14 days
old (two missed weekly cycles).

Job URL convention: since HVAPS listings have no individual web pages, each job's
URL is anchored on the official bulletin page using the job's unique MEM-NNN-YY
ID as a fragment.  This produces a unique guid per job in the DB.

Field notes (from JSON inventory, April 2026):
  id            — MEM-NNN-YY, stable unique ID, always present
  position_title — job title, always present
  office         — member name or committee ("Office of Congressman X", "Senior
                   House Financial Services Republican"), always present
  location       — "Washington, D.C." or district office city, 25/27 present
  posting_date   — ISO YYYY-MM-DD (bulletin date), always present
  description    — full prose, always present
  responsibilities — list of bullet strings, always a list
  qualifications   — list of bullet strings, always a list
  salary_info    — free-text range string, 18/27 present
  how_to_apply   — email/URL + deadline text, always present (closing date
                   embedded here as prose — no structured closing_date field)
  contact        — mixed type (dict {"url": ...} or email string), 25/27 present
                   redundant with how_to_apply; not used separately
  equal_opportunity — EEO boilerplate, 22/27 present; not included in description
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import date, datetime, timezone

import httpx

from src.models.job import Job
from src.scrapers.base import BaseScraper, USER_AGENT, REQUEST_DELAY

log = logging.getLogger(f"scraper.{__name__.split('.')[-1]}")

GITHUB_API_DIR = (
    "https://api.github.com/repos/dwillis/house-jobs/contents/json_gemini_flash"
)
BULLETIN_BASE_URL = (
    "https://www.house.gov/employment/positions-with-members-and-committees"
)

# Matches the trailing month_day_year portion of HVAPS filenames:
#   HVAPS_Template_Members_2026_04_20_2026.json  →  04, 20, 2026
#   HVAPS_Template_Members_2025_1_05_2026.json   →   1, 05, 2026
_DATE_RE = re.compile(r"_(\d{1,2})_(\d{1,2})_(\d{4})\.json$")

# Number of recent bulletins to fetch per run (roughly one month of coverage)
BULLETINS_TO_FETCH = 4

# Emit upstream_stale alert after this many days without a new bulletin
STALE_THRESHOLD_DAYS = 14


def _parse_bulletin_date(filename: str) -> date | None:
    m = _DATE_RE.search(filename)
    if not m:
        return None
    month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _build_description(entry: dict) -> str:
    """Combine available fields into a human-readable description string."""
    parts: list[str] = []

    if desc := (entry.get("description") or "").strip():
        parts.append(desc)

    # responsibilities is always a list per field inventory
    if resp := entry.get("responsibilities"):
        if isinstance(resp, list) and resp:
            lines = "; ".join(r.strip() for r in resp[:6] if r.strip())
            if lines:
                parts.append(f"Responsibilities: {lines}")
        elif isinstance(resp, str) and resp.strip():
            parts.append(f"Responsibilities: {resp.strip()}")

    # qualifications is always a list per field inventory
    if qual := entry.get("qualifications"):
        if isinstance(qual, list) and qual:
            lines = "; ".join(q.strip() for q in qual[:5] if q.strip())
            if lines:
                parts.append(f"Qualifications: {lines}")
        elif isinstance(qual, str) and qual.strip():
            parts.append(f"Qualifications: {qual.strip()}")

    # salary_info present in ~67% of entries — include when available
    if salary := (entry.get("salary_info") or "").strip():
        parts.append(f"Salary: {salary}")

    if apply := (entry.get("how_to_apply") or "").strip():
        parts.append(f"How to apply: {apply}")

    return "\n\n".join(parts)


class Scraper(BaseScraper):
    """Scraper for the House HVAPS Employment Bulletin via dwillis/house-jobs JSON."""

    #: Set after scrape() — picked up by pipeline.py to populate per-source results
    #: and trigger upstream_stale alerts via generate_alerts().
    upstream_meta: dict | None = None

    async def scrape(self) -> list[Job]:
        partisan_lean = self.source.get("partisan_lean", "unknown")

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token := os.environ.get("GITHUB_TOKEN", "").strip():
            headers["Authorization"] = f"Bearer {token}"

        # 1. List all JSON files in the json_gemini_flash directory
        async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
            r = await client.get(GITHUB_API_DIR)
            r.raise_for_status()
            files = r.json()
            await asyncio.sleep(REQUEST_DELAY)

        # 2. Parse dates and identify the N most recent bulletins
        dated: list[tuple[date, str]] = []
        for f in files:
            if not isinstance(f, dict) or not f.get("name", "").endswith(".json"):
                continue
            d = _parse_bulletin_date(f["name"])
            if d and (download_url := f.get("download_url")):
                dated.append((d, download_url))

        if not dated:
            log.warning("No parseable JSON files found in dwillis/house-jobs")
            self.upstream_meta = {
                "upstream_stale": True,
                "upstream_last_bulletin": None,
                "upstream_days_since_update": None,
            }
            return []

        dated.sort(key=lambda x: x[0], reverse=True)
        most_recent_date = dated[0][0]
        today = datetime.now(timezone.utc).date()
        days_since = (today - most_recent_date).days
        is_stale = days_since > STALE_THRESHOLD_DAYS

        self.upstream_meta = {
            "upstream_stale": is_stale,
            "upstream_last_bulletin": str(most_recent_date),
            "upstream_days_since_update": days_since,
        }

        if is_stale:
            log.warning(
                f"House Employment Bulletin: upstream is {days_since} days old "
                f"(last bulletin: {most_recent_date}, threshold: {STALE_THRESHOLD_DAYS} days). "
                "dwillis/house-jobs may be unmaintained — verify manually."
            )

        to_fetch = dated[:BULLETINS_TO_FETCH]
        log.info(
            "Fetching %d House bulletin(s): %s",
            len(to_fetch),
            ", ".join(str(d) for d, _ in to_fetch),
        )

        # 3. Download and parse bulletins
        seen_ids: set[str] = set()
        jobs: list[Job] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            for bulletin_date, download_url in to_fetch:
                try:
                    r = await client.get(download_url)
                    r.raise_for_status()
                    await asyncio.sleep(REQUEST_DELAY)
                except httpx.HTTPError as exc:
                    log.error(f"Failed to fetch bulletin {bulletin_date}: {exc}")
                    continue

                try:
                    entries = r.json()
                except Exception as exc:
                    log.error(f"Failed to parse bulletin {bulletin_date}: {exc}")
                    continue

                if not isinstance(entries, list):
                    log.warning(f"Unexpected format in bulletin {bulletin_date}")
                    continue

                for entry in entries:
                    job_id = (entry.get("id") or "").strip()
                    if not job_id or job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    title = (entry.get("position_title") or "").strip()
                    if not title:
                        continue

                    office = (
                        (entry.get("office") or "").strip()
                        or "US House of Representatives"
                    )
                    location = (entry.get("location") or "").strip() or None
                    posting_date_raw = entry.get("posting_date") or str(bulletin_date)
                    description = _build_description(entry)

                    # Fragment anchor → unique guid per posting while linking to
                    # the authoritative House bulletin page.
                    job_url = f"{BULLETIN_BASE_URL}#{job_id}"

                    jobs.append(
                        Job(
                            title=title,
                            url=job_url,
                            organisation=office,
                            description=description,
                            source_name=self.name,
                            category=self.category,
                            country=self.country,
                            location=location,
                            partisan_lean=partisan_lean,
                            date_scraped=posting_date_raw,
                        )
                    )

        log.info("Total: %d jobs from %d bulletin(s)", len(jobs), len(to_fetch))
        return jobs
