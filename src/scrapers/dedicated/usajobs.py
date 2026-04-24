"""
USAJobs dedicated scraper.

Uses the official USAJobs REST API (no HTML scraping).
Authentication: USAJOBS_USER_AGENT (registrant email) and USAJOBS_API_KEY env vars.
Free developer key: https://developer.usajobs.gov/APIRequest/Index

Two query modes (controlled by source config):
  Series-code mode (default):
    Queries the API by JobCategoryCode, then applies a keyword post-filter.
    Used for the main us-federal feed.

  Keyword mode (keyword_queries: [...] in source config):
    Queries the API using the Keyword parameter; keyword post-filter is skipped
    because the query term is itself the relevance signal.
    Used for the us-fellowships feed.

Series codes can be overridden per source entry via series_codes: [...].
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
TOTAL_CAP = 500  # per source; overrides the global 200-per-source default

# Occupational series codes relevant to policy and government affairs work
DEFAULT_SERIES_CODES = [
    "0110",  # Economist
    "0130",  # Foreign Affairs
    "0131",  # International Relations
    "0301",  # Miscellaneous Administration and Program
    "0340",  # Program Management
    "0343",  # Management and Program Analysis
    "1035",  # Public Affairs
]

# A job passes the filter if title or summary contains at least one of these.
# Only applied in series-code mode; keyword mode bypasses this filter.
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


def _build_job(item: dict, source_name: str, category: str, country: str,
               partisan_lean: str | None) -> Job | None:
    """Build a Job from a single SearchResultItem dict.  Returns None if
    required fields are missing."""
    d = item.get("MatchedObjectDescriptor", {})
    title = (d.get("PositionTitle") or "").strip()
    url = (d.get("PositionURI") or "").strip()
    if not title or not url:
        return None

    user_area = d.get("UserArea") or {}
    details = user_area.get("Details") or {}
    summary = (details.get("JobSummary") or "").strip()

    org = (
        d.get("OrganizationName") or d.get("DepartmentName") or "US Federal Government"
    ).strip()

    locations = d.get("PositionLocation") or []
    location = locations[0].get("LocationName") if locations else None

    remuneration = d.get("PositionRemuneration") or []
    salary_info = ""
    if remuneration:
        r0 = remuneration[0]
        min_r, max_r = r0.get("MinimumRange", ""), r0.get("MaximumRange", "")
        rate = r0.get("RateIntervalCode", "")
        if min_r and max_r:
            try:
                salary_info = f"${float(min_r):,.0f}–${float(max_r):,.0f} {rate}".strip()
            except ValueError:
                salary_info = f"{min_r}–{max_r} {rate}".strip()

    grades = d.get("JobGrade") or []
    grade = grades[0].get("Code", "") if grades else ""

    desc_parts = []
    if summary:
        desc_parts.append(summary[:300])
    if salary_info:
        desc_parts.append(f"Salary: {salary_info}")
    if grade:
        desc_parts.append(f"Grade: {grade}")
    description = " | ".join(desc_parts)[:500] or f"{org} — {title}"

    closing_date = _parse_iso_date(d.get("ApplicationCloseDate", ""))

    return Job(
        title=title,
        url=url,
        organisation=org,
        description=description,
        source_name=source_name,
        category=category,
        country=country,
        location=location,
        closing_date=closing_date,
        partisan_lean=partisan_lean,
    )


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
        total_cap = int(self.source.get("total_cap", TOTAL_CAP))

        # Query mode: keyword or series-code
        keyword_queries: list[str] = self.source.get("keyword_queries") or []
        series_codes: list[str] = self.source.get("series_codes") or DEFAULT_SERIES_CODES
        use_keyword_mode = bool(keyword_queries)

        headers = {
            "Host": "data.usajobs.gov",
            "User-Agent": user_agent_email,
            "Authorization-Key": api_key,
            "Content-Type": "application/json",
        }

        all_jobs: list[Job] = []
        seen_ids: set[str] = set()

        # Build the list of query parameter dicts to iterate over
        if use_keyword_mode:
            query_list = [{"Keyword": kw} for kw in keyword_queries]
            mode_label = f"keywords: {', '.join(keyword_queries)}"
        else:
            query_list = [{"JobCategoryCode": sc} for sc in series_codes]
            mode_label = f"series: {', '.join(series_codes)}"

        async with httpx.AsyncClient(
            headers=headers, follow_redirects=True, timeout=30.0
        ) as client:
            for query_params in query_list:
                if len(all_jobs) >= total_cap:
                    break

                page = 1
                while True:
                    if len(all_jobs) >= total_cap:
                        break

                    params = {
                        **query_params,
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
                        query_id = list(query_params.values())[0]
                        self.log.error(f"API error fetching {query_id} page {page}: {exc}")
                        break

                    data = r.json()
                    search_result = data.get("SearchResult", {})
                    items = search_result.get("SearchResultItems", [])
                    total_count = int(search_result.get("SearchResultCountAll", 0))

                    if not items:
                        break

                    for item in items:
                        if len(all_jobs) >= total_cap:
                            break

                        job_id = item.get("MatchedObjectId", "")
                        if not job_id or job_id in seen_ids:
                            continue

                        # Series-code mode: apply keyword relevance filter
                        if not use_keyword_mode:
                            d = item.get("MatchedObjectDescriptor", {})
                            title = (d.get("PositionTitle") or "").strip()
                            summary = (
                                (d.get("UserArea") or {})
                                .get("Details", {})
                                .get("JobSummary", "") or ""
                            ).strip()
                            if not _passes_keyword_filter(title, summary):
                                continue

                        job = _build_job(
                            item, self.name, self.category, self.country, partisan_lean
                        )
                        if job:
                            seen_ids.add(job_id)
                            all_jobs.append(job)

                    fetched = page * RESULTS_PER_PAGE
                    if not items or fetched >= total_count or len(items) < RESULTS_PER_PAGE:
                        break
                    page += 1

        self.log.info(f"Total: {len(all_jobs)} jobs ({mode_label})")
        return all_jobs
