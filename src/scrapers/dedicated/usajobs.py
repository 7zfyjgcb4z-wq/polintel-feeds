"""
USAJobs dedicated scraper.

Uses the official USAJobs REST API (no HTML scraping).
Authentication: USAJOBS_USER_AGENT (registrant email) and USAJOBS_API_KEY env vars.
Free developer key: https://developer.usajobs.gov/APIRequest/Index

Hybrid filter strategy:
  1. Query by policy-relevant occupational series codes (JobCategoryCode).
  2. Apply keyword post-filter on title + job summary.
  3. Hard cap: 500 most recent across all series codes.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime

import httpx

from src.models.job import Job
from src.scrapers.base import BaseScraper, REQUEST_DELAY

API_URL = "https://data.usajobs.gov/api/Search"
RESULTS_PER_PAGE = 100
TOTAL_CAP = 500  # USAJobs-specific; overrides the global 200-per-source default

# Occupational series codes relevant to policy and government affairs work
SERIES_CODES = [
    "0110",  # Economist
    "0130",  # Foreign Affairs
    "0131",  # International Relations
    "0301",  # Miscellaneous Administration and Program
    "0340",  # Program Management
    "0343",  # Management and Program Analysis
    "1035",  # Public Affairs
]

# A job passes the filter if title or summary contains at least one of these
KEYWORD_FILTER = frozenset([
    "policy", "legislative", "congressional", "political", "diplomat",
    "intelligence analyst", "international", "foreign", "public affairs",
    "government relations", "advocacy", "regulatory",
])


def _passes_keyword_filter(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    return any(kw in text for kw in KEYWORD_FILTER)


def _parse_iso_date(raw: str) -> str | None:
    """Parse USAJobs date strings like '2026-05-10T00:00:00' → '2026-05-10'."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.rstrip("Z").split("T")[0]).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        api_key = os.environ.get("USAJOBS_API_KEY", "").strip()
        user_agent_email = os.environ.get("USAJOBS_USER_AGENT", "").strip()
        if not api_key or not user_agent_email:
            raise EnvironmentError(
                "USAJOBS_API_KEY and USAJOBS_USER_AGENT env vars are required. "
                "Obtain a free key at https://developer.usajobs.gov/APIRequest/Index"
            )

        partisan_lean = self.source.get("partisan_lean")

        headers = {
            "Host": "data.usajobs.gov",
            "User-Agent": user_agent_email,
            "Authorization-Key": api_key,
            "Content-Type": "application/json",
        }

        all_jobs: list[Job] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(
            headers=headers, follow_redirects=True, timeout=30.0
        ) as client:
            for series_code in SERIES_CODES:
                if len(all_jobs) >= TOTAL_CAP:
                    break

                page = 1
                while True:
                    if len(all_jobs) >= TOTAL_CAP:
                        break

                    params = {
                        "JobCategoryCode": series_code,
                        "ResultsPerPage": RESULTS_PER_PAGE,
                        "Page": page,
                        "SortField": "DatePosted",
                        "SortDirection": "Desc",
                    }

                    try:
                        r = await client.get(API_URL, params=params)
                        r.raise_for_status()
                        await asyncio.sleep(REQUEST_DELAY)
                    except httpx.HTTPError as exc:
                        self.log.error(
                            f"API error fetching series {series_code} page {page}: {exc}"
                        )
                        break

                    data = r.json()
                    search_result = data.get("SearchResult", {})
                    items = search_result.get("SearchResultItems", [])
                    total_count = int(search_result.get("SearchResultCountAll", 0))

                    if not items:
                        break

                    for item in items:
                        if len(all_jobs) >= TOTAL_CAP:
                            break

                        d = item.get("MatchedObjectDescriptor", {})
                        job_id = item.get("MatchedObjectId", "")
                        if not job_id or job_id in seen_ids:
                            continue
                        seen_ids.add(job_id)

                        title = (d.get("PositionTitle") or "").strip()
                        url = (d.get("PositionURI") or "").strip()
                        if not title or not url:
                            continue

                        # Job summary from UserArea.Details
                        summary = ""
                        user_area = d.get("UserArea") or {}
                        details = user_area.get("Details") or {}
                        summary = (details.get("JobSummary") or "").strip()

                        if not _passes_keyword_filter(title, summary):
                            continue

                        org = (
                            d.get("OrganizationName")
                            or d.get("DepartmentName")
                            or "US Federal Government"
                        ).strip()

                        locations = d.get("PositionLocation") or []
                        location = (
                            locations[0].get("LocationName") if locations else None
                        )

                        # Salary: "$min–$max per year" if available
                        salary_info = ""
                        remuneration = d.get("PositionRemuneration") or []
                        if remuneration:
                            r0 = remuneration[0]
                            min_r = r0.get("MinimumRange", "")
                            max_r = r0.get("MaximumRange", "")
                            rate = r0.get("RateIntervalCode", "")
                            if min_r and max_r:
                                try:
                                    salary_info = (
                                        f"${float(min_r):,.0f}–${float(max_r):,.0f} {rate}"
                                    ).strip()
                                except ValueError:
                                    salary_info = f"{min_r}–{max_r} {rate}".strip()

                        # Grade (e.g. "GS-13")
                        grade = ""
                        grades = d.get("JobGrade") or []
                        if grades:
                            grade = grades[0].get("Code", "")

                        # Build description from summary + salary + grade
                        desc_parts = []
                        if summary:
                            desc_parts.append(summary[:300])
                        if salary_info:
                            desc_parts.append(f"Salary: {salary_info}")
                        if grade:
                            desc_parts.append(f"Grade: {grade}")
                        description = " | ".join(desc_parts)[:500] or f"{org} — {title}"

                        closing_date = _parse_iso_date(
                            d.get("ApplicationCloseDate", "")
                        )

                        all_jobs.append(
                            Job(
                                title=title,
                                url=url,
                                organisation=org,
                                description=description,
                                source_name=self.name,
                                category=self.category,
                                country=self.country,
                                location=location,
                                closing_date=closing_date,
                                partisan_lean=partisan_lean,
                            )
                        )

                    # Pagination: stop if all results fetched
                    fetched = page * RESULTS_PER_PAGE
                    if not items or fetched >= total_count or len(items) < RESULTS_PER_PAGE:
                        break
                    page += 1

        self.log.info(
            f"Total: {len(all_jobs)} jobs after keyword filter "
            f"(series: {', '.join(SERIES_CODES)})"
        )
        return all_jobs
