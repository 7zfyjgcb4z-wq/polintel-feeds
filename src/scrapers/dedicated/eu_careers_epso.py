"""
EU Careers (EPSO) scraper.

Fetches https://eu-careers.europa.eu/en/job-opportunities/open-for-application
and parses server-rendered HTML job listings.
Tries a JSON/API endpoint first; falls back to HTML parsing.
"""
from __future__ import annotations

import asyncio
import re

import httpx
from bs4 import BeautifulSoup

from src.models.job import Job
from src.scrapers.base import BaseScraper, USER_AGENT, REQUEST_DELAY

BASE = "https://eu-careers.europa.eu"
JOBS_URL = f"{BASE}/en/job-opportunities/open-for-application"
MAX_JOBS = 200


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        try:
            return await self._scrape()
        except Exception as e:
            self.log.error(f"EU Careers scrape failed: {e}")
            return []

    async def _scrape(self) -> list[Job]:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            # Try JSON API first
            jobs = await self._try_json_api(client)
            if jobs:
                return jobs

            # Fall back to HTML parsing
            return await self._parse_html(client)

    async def _try_json_api(self, client: httpx.AsyncClient) -> list[Job]:
        """Try known EPSO API endpoints."""
        api_candidates = [
            f"{BASE}/api/job-opportunities",
            f"{BASE}/en/job-opportunities/open-for-application.json",
            f"{BASE}/api/v1/competitions",
        ]
        for url in api_candidates:
            try:
                r = await client.get(url, headers={"Accept": "application/json"})
                if r.status_code == 200:
                    data = r.json()
                    jobs = self._parse_json(data)
                    if jobs:
                        self.log.info(f"JSON API succeeded: {url}")
                        return jobs
                await asyncio.sleep(REQUEST_DELAY)
            except Exception:
                continue
        return []

    def _parse_json(self, data) -> list[Job]:
        jobs: list[Job] = []
        items = data if isinstance(data, list) else data.get("data", data.get("items", []))
        if not isinstance(items, list):
            return []
        for item in items[:MAX_JOBS]:
            title = (
                item.get("title") or item.get("name") or item.get("competition_name", "")
            )
            if not title:
                continue
            url = item.get("url") or item.get("link") or item.get("apply_url", "")
            if not url:
                job_id = item.get("id") or item.get("reference", "")
                url = f"{JOBS_URL}#{job_id}" if job_id else JOBS_URL
            if not url.startswith("http"):
                url = f"{BASE}{url}"
            org = item.get("institution") or item.get("body") or "EU Institution"
            location = item.get("location") or item.get("place") or "Brussels"
            closing = item.get("deadline") or item.get("closing_date") or None
            jobs.append(
                Job(
                    title=title,
                    url=url,
                    organisation=org,
                    description=f"{org} | {location}"[:500],
                    source_name=self.name,
                    category=self.category,
                    country=self.country,
                    location=location,
                    closing_date=closing,
                )
            )
        return jobs

    async def _parse_html(self, client: httpx.AsyncClient) -> list[Job]:
        jobs: list[Job] = []
        seen_urls: set[str] = set()

        try:
            r = await client.get(JOBS_URL)
            r.raise_for_status()
            await asyncio.sleep(REQUEST_DELAY)
        except httpx.HTTPError as e:
            self.log.error(f"HTML fetch failed: {e}")
            return []

        soup = BeautifulSoup(r.text, "lxml")

        # EPSO pages typically use Bootstrap cards or table rows
        containers = (
            soup.select(".competition-item")
            or soup.select(".job-opportunity")
            or soup.select(".card")
            or soup.select("tr[class*='competition']")
            or soup.select("tr[class*='job']")
        )

        # Fallback: any container with a link to a competition detail
        if not containers:
            containers = [
                a.parent
                for a in soup.find_all(
                    "a", href=re.compile(r"/competition|/job-opportunit|/vacancy")
                )
                if a.parent
            ]

        for item in containers:
            link = item.find("a", href=True)
            if not link:
                continue

            title = link.get_text(strip=True)
            if not title:
                title_h = item.find(["h2", "h3", "h4"])
                title = title_h.get_text(strip=True) if title_h else ""
            if not title:
                continue

            href = link.get("href", "")
            url = href if href.startswith("http") else f"{BASE}{href}"
            if url in seen_urls:
                continue
            seen_urls.add(url)

            org_el = item.find(class_=re.compile(r"institution|body|organ", re.I))
            org = org_el.get_text(strip=True) if org_el else "EU Institution"

            loc_el = item.find(class_=re.compile(r"locat|place|city", re.I))
            location = loc_el.get_text(strip=True) if loc_el else "Brussels"

            date_el = item.find(class_=re.compile(r"deadline|closing|date", re.I))
            closing = date_el.get_text(strip=True) if date_el else None

            jobs.append(
                Job(
                    title=title,
                    url=url,
                    organisation=org,
                    description=f"{org} | {location}"[:500],
                    source_name=self.name,
                    category=self.category,
                    country=self.country,
                    location=location,
                    closing_date=closing,
                )
            )
            if len(jobs) >= MAX_JOBS:
                break

        self.log.info(f"HTML parse: {len(jobs)} jobs")
        return jobs
