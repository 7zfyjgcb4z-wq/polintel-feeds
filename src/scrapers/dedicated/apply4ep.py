"""
APPLY4EP (European Parliament) scraper.

Fetches https://apply4ep.gestmax.eu/search/offers
Gestmax ATS — tries a JSON API first (common for Gestmax), falls back to HTML.
"""
from __future__ import annotations

import asyncio
import re

import httpx
from bs4 import BeautifulSoup

from src.models.job import Job
from src.scrapers.base import BaseScraper, USER_AGENT, REQUEST_DELAY

BASE = "https://apply4ep.gestmax.eu"
JOBS_URL = f"{BASE}/search/offers"
MAX_JOBS = 200


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        try:
            return await self._scrape()
        except Exception as e:
            self.log.error(f"APPLY4EP scrape failed: {e}")
            return []

    async def _scrape(self) -> list[Job]:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            # Try JSON API endpoints common to Gestmax ATS
            jobs = await self._try_json_api(client)
            if jobs:
                return jobs

            # Fall back to HTML
            return await self._parse_html(client)

    async def _try_json_api(self, client: httpx.AsyncClient) -> list[Job]:
        api_candidates = [
            f"{BASE}/api/offers",
            f"{BASE}/api/jobs",
            f"{BASE}/search/offers.json",
            f"{BASE}/api/v1/offers",
        ]
        for url in api_candidates:
            try:
                r = await client.get(url, headers={"Accept": "application/json"})
                if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
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
        items = data if isinstance(data, list) else data.get("offers", data.get("data", data.get("results", [])))
        if not isinstance(items, list):
            return []
        for item in items[:MAX_JOBS]:
            title = item.get("title") or item.get("name") or item.get("label", "")
            if not title:
                continue
            offer_id = item.get("id") or item.get("reference", "")
            url = item.get("url") or item.get("link") or (
                f"{BASE}/search/offers/{offer_id}" if offer_id else JOBS_URL
            )
            if not url.startswith("http"):
                url = f"{BASE}{url}"
            org = item.get("department") or item.get("organisation") or "European Parliament"
            location = item.get("location") or item.get("city") or "Brussels"
            closing = item.get("deadline") or item.get("closing_date") or None
            contract = item.get("contract_type") or item.get("type") or ""
            desc = f"{org} | {location}"
            if contract:
                desc += f" | {contract}"
            jobs.append(
                Job(
                    title=title,
                    url=url,
                    organisation=org,
                    description=desc[:500],
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

        # Gestmax typically uses .offer-item, .offre, or table rows
        containers = (
            soup.select(".offer-item")
            or soup.select(".offre")
            or soup.select(".job-offer")
            or soup.select("tr.offer")
            or soup.select("li.offer")
            or soup.select("[class*='offer']")
        )

        if not containers:
            # Fallback: any link pointing to an offer detail page
            containers = [
                a.parent
                for a in soup.find_all(
                    "a", href=re.compile(r"/search/offers/\d|/offer/\d")
                )
                if a.parent
            ]

        for item in containers:
            link = item.find("a", href=re.compile(r"/offer|/offre|\d{4,}"))
            if not link:
                link = item.find("a", href=True)
            if not link:
                continue

            title = link.get_text(strip=True)
            if not title:
                h = item.find(["h2", "h3", "h4"])
                title = h.get_text(strip=True) if h else ""
            if not title:
                continue

            href = link.get("href", "")
            url = href if href.startswith("http") else f"{BASE}{href}"
            if url in seen_urls:
                continue
            seen_urls.add(url)

            org_el = item.find(class_=re.compile(r"dept|depart|unit|organ|institution", re.I))
            org = org_el.get_text(strip=True) if org_el else "European Parliament"

            loc_el = item.find(class_=re.compile(r"locat|place|city", re.I))
            location = loc_el.get_text(strip=True) if loc_el else "Brussels"

            date_el = item.find(class_=re.compile(r"deadline|closing|date|expire", re.I))
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
