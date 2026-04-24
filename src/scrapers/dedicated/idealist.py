"""
Idealist dedicated scraper.

Uses the Idealist Open Network API (v1).
Authentication: Basic auth with IDEALIST_API_KEY as username, empty password.
Partner key required — apply at https://www.idealist.org/en/open-network-api

API pagination: cursor-based via `since` (ISO 8601 timestamp), not page numbers.
Filter strategy:
  1. Fetch all jobs updated in the last 30 days via cursor pagination.
  2. Pre-filter by title keywords to reduce expensive detail fetches.
  3. Fetch job details; filter by US country and relevant areasOfFocus.
  4. Exclude direct-service roles by title/description.
  5. Cap at 200 jobs.

Note: Playwright is not used — the site is JS-rendered but the JSON API bypasses that.
"""
from __future__ import annotations

import asyncio
import base64
import os
from datetime import datetime, timedelta, timezone

import httpx

from src.models.job import Job
from src.scrapers.base import BaseScraper, REQUEST_DELAY

API_BASE = "https://www.idealist.org/api/v1"
JOB_CAP = 200
DAYS_LOOKBACK = 30

# areasOfFocus codes that indicate policy/advocacy relevance
RELEVANT_AREAS = frozenset([
    "POLICY_AND_ADVOCACY",
    "GOVERNMENT_RELATIONS",
    "CIVIL_RIGHTS_SOCIAL_ACTION",
    "INTERNATIONAL_RELATIONS",
    "COMMUNITY_ORGANIZING",
    "CIVIC_ENGAGEMENT",
    "HUMAN_RIGHTS",
    "IMMIGRATION",
    "ENVIRONMENT",
    "HEALTH_POLICY",
    "EDUCATION_POLICY",
])

# Title/description keywords suggesting direct service delivery (exclude these
# unless the title also mentions policy, advocacy, government, or public affairs)
_DIRECT_SERVICE_TERMS = frozenset([
    "case manager", "case worker", "caseworker", "social worker",
    "therapist", "counselor", "counsellor", "nurse", "nursing",
    "home health", "direct support", "direct care", "classroom teacher",
    "teacher aide", "teaching assistant", "food service", "janitorial",
    "custodian", "security guard", "receptionist",
])

_POLICY_RESCUE_TERMS = frozenset([
    "policy", "advocacy", "government", "public affairs", "legislative",
    "regulatory", "political",
])

# Title keywords that suggest policy relevance — used as pre-filter before
# fetching expensive job detail pages
_TITLE_INCLUDE_TERMS = frozenset([
    "policy", "advocacy", "advocate", "government", "affairs", "legislative",
    "campaign", "political", "organiz", "outreach", "research", "director",
    "analyst", "fellow", "intern", "manager", "coordinator", "strategist",
    "communications", "press", "media", "legal", "counsel", "counsel",
    "engagement", "mobiliz", "coalition",
])


def _is_direct_service(title: str, description: str = "") -> bool:
    text = (title + " " + description).lower()
    if not any(term in text for term in _DIRECT_SERVICE_TERMS):
        return False
    # Rescue: if role mentions policy/advocacy it's still relevant
    return not any(term in text for term in _POLICY_RESCUE_TERMS)


def _title_is_candidate(title: str) -> bool:
    """Pre-filter: does the job title look potentially relevant?"""
    text = title.lower()
    return any(term in text for term in _TITLE_INCLUDE_TERMS)


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        api_key = os.environ.get("IDEALIST_API_KEY", "").strip()
        if not api_key:
            self.log.warning(
                "IDEALIST_API_KEY not set — Idealist requires a partner API key. "
                "Apply at https://www.idealist.org/en/open-network-api. "
                "Returning 0 jobs."
            )
            return []

        partisan_lean = self.source.get("partisan_lean")

        credentials = base64.b64encode(f"{api_key}:".encode()).decode()
        headers = {
            "Authorization": f"Basic {credentials}",
            "Accept": "application/json",
        }

        # Cursor: fetch jobs updated within the last DAYS_LOOKBACK days
        since = (
            datetime.now(timezone.utc) - timedelta(days=DAYS_LOOKBACK)
        ).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        candidate_stubs: list[dict] = []

        async with httpx.AsyncClient(
            headers=headers, follow_redirects=True, timeout=30.0
        ) as client:
            # ── Phase 1: paginate job list, pre-filter by title ──────────────
            cursor = since
            while True:
                try:
                    r = await client.get(
                        f"{API_BASE}/listings/jobs",
                        params={"since": cursor, "limit": 100},
                    )
                    r.raise_for_status()
                    await asyncio.sleep(REQUEST_DELAY)
                except httpx.HTTPStatusError as exc:
                    self.log.error(
                        f"Idealist list API error {exc.response.status_code}: {exc}"
                    )
                    break
                except httpx.HTTPError as exc:
                    self.log.error(f"Idealist list API network error: {exc}")
                    break

                data = r.json()
                batch = data.get("jobs", [])
                if not batch:
                    break

                for stub in batch:
                    name = stub.get("name", "")
                    if _title_is_candidate(name) and not _is_direct_service(name):
                        candidate_stubs.append(stub)

                if not data.get("hasMore", False):
                    break

                # Advance cursor to last item's updated timestamp
                last_updated = batch[-1].get("updated", "")
                if not last_updated or last_updated == cursor:
                    break
                cursor = last_updated

            self.log.info(
                f"{len(candidate_stubs)} candidate stubs after title pre-filter"
            )

            # ── Phase 2: fetch details, filter by US + areasOfFocus ──────────
            jobs: list[Job] = []
            seen_ids: set[str] = set()

            for stub in candidate_stubs:
                if len(jobs) >= JOB_CAP:
                    break

                job_id = stub.get("id", "")
                if not job_id or job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                try:
                    r = await client.get(f"{API_BASE}/listings/jobs/{job_id}")
                    r.raise_for_status()
                    await asyncio.sleep(REQUEST_DELAY)
                except httpx.HTTPError as exc:
                    self.log.warning(f"Detail fetch failed for job {job_id}: {exc}")
                    continue

                detail = r.json()

                # Filter: US-based or US-remote
                org_data = detail.get("org") or {}
                address = org_data.get("address") or {}
                country_code = (address.get("country") or "").upper()
                remote_country = (detail.get("remoteCountry") or "").upper()
                location_type = detail.get("locationType", "")

                is_us = (
                    country_code == "US"
                    or remote_country == "US"
                    or (location_type == "REMOTE" and not remote_country)
                )
                if not is_us:
                    continue

                # Filter: at least one relevant area of focus
                areas = {
                    a.get("code", "")
                    for a in (detail.get("areasOfFocus") or [])
                }
                if not (areas & RELEVANT_AREAS):
                    continue

                title = (detail.get("name") or stub.get("name", "")).strip()
                if not title:
                    continue

                # URL: prefer English
                url_data = stub.get("url") or detail.get("url") or {}
                url = url_data.get("en", "")
                if not url:
                    continue
                if not url.startswith("http"):
                    url = f"https://www.idealist.org{url}"

                # For apply URL, prefer applyUrl if set
                apply_url = (detail.get("applyUrl") or url).strip() or url

                org_name = (org_data.get("name") or "Idealist").strip()

                city = (address.get("city") or "").strip()
                state = (address.get("state") or "").strip()
                location = ", ".join(filter(None, [city, state])) or None

                raw_desc = (detail.get("description") or "").strip()
                if not raw_desc:
                    funcs = [
                        f.get("name", "")
                        for f in (detail.get("functions") or [])
                    ]
                    raw_desc = (
                        f"{org_name} — {', '.join(f for f in funcs if f)}"
                        if funcs
                        else org_name
                    )
                description = raw_desc[:500]

                closing_raw = detail.get("applicationDeadline") or ""
                closing_date = closing_raw[:10] if closing_raw else None

                if _is_direct_service(title, description):
                    continue

                jobs.append(
                    Job(
                        title=title,
                        url=apply_url,
                        organisation=org_name,
                        description=description,
                        source_name=self.name,
                        category=self.category,
                        country=self.country,
                        location=location,
                        closing_date=closing_date,
                        partisan_lean=partisan_lean,
                    )
                )

        self.log.info(
            f"Total: {len(jobs)} US policy jobs after areasOfFocus + service filter"
        )
        return jobs
