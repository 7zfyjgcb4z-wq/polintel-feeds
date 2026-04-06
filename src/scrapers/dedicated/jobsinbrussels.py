"""
Jobs in Brussels scraper.

Parses https://jobsin.brussels/jobs — standard HTML job listing page.
Falls back gracefully if structure changes.
"""
from __future__ import annotations

import asyncio
import re

import httpx
from bs4 import BeautifulSoup

from src.models.job import Job
from src.scrapers.base import BaseScraper, USER_AGENT, REQUEST_DELAY

BASE = "https://jobsin.brussels"
JOBS_URL = f"{BASE}/"
MAX_JOBS = 200


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        try:
            return await self._scrape()
        except Exception as e:
            self.log.error(f"Jobs in Brussels scrape failed: {e}")
            return []

    async def _scrape(self) -> list[Job]:
        jobs: list[Job] = []
        seen_urls: set[str] = set()

        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            # Try JSON API first
            for api_url in [f"{BASE}/api/jobs", f"{BASE}/api/v1/jobs", f"{BASE}/jobs.json"]:
                try:
                    r = await client.get(api_url, headers={"Accept": "application/json"})
                    if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
                        data = r.json()
                        items = data if isinstance(data, list) else data.get("jobs", data.get("data", []))
                        if items:
                            self.log.info(f"JSON API: {api_url}")
                            for item in items[:MAX_JOBS]:
                                job = self._from_json(item)
                                if job:
                                    jobs.append(job)
                            self.log.info(f"Total: {len(jobs)} jobs")
                            return jobs
                    await asyncio.sleep(REQUEST_DELAY)
                except Exception:
                    continue

            # Fall back to HTML pagination
            page = 1
            while len(jobs) < MAX_JOBS:
                url = JOBS_URL if page == 1 else f"{JOBS_URL}?page={page}"
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    await asyncio.sleep(REQUEST_DELAY)
                except httpx.HTTPError as e:
                    self.log.error(f"Fetch error page {page}: {e}")
                    break

                soup = BeautifulSoup(r.text, "lxml")
                page_jobs = self._parse_page(soup, seen_urls)

                if not page_jobs:
                    break

                jobs.extend(page_jobs)
                self.log.debug(f"Page {page}: {len(page_jobs)} jobs (total {len(jobs)})")

                if not self._has_next(soup):
                    break
                page += 1

        self.log.info(f"Total: {len(jobs)} jobs")
        return jobs[:MAX_JOBS]

    def _from_json(self, item: dict) -> Job | None:
        title = item.get("title") or item.get("name") or item.get("position", "")
        if not title:
            return None
        url = item.get("url") or item.get("link") or item.get("apply_url", "")
        if not url:
            job_id = item.get("id", "")
            url = f"{BASE}/job/{job_id}" if job_id else BASE
        if not url.startswith("http"):
            url = f"{BASE}{url}"
        org = item.get("company") or item.get("organisation") or item.get("employer", "Jobs in Brussels")
        location = item.get("location") or item.get("city", "Brussels")
        return Job(
            title=title,
            url=url,
            organisation=org,
            description=f"{org} | {location}"[:500],
            source_name=self.name,
            category=self.category,
            country=self.country,
            location=location,
        )

    def _parse_page(self, soup: BeautifulSoup, seen_urls: set[str]) -> list[Job]:
        jobs: list[Job] = []

        # Try common job-listing selectors in order of specificity
        containers = (
            soup.select(".job-listing")
            or soup.select("article.job")
            or soup.select(".job-item")
            or soup.select("[class*='job-card']")
            or soup.select("[class*='vacancy']")
            or soup.select("li.job")
        )

        # If no specific containers, try any element with a job-detail link
        if not containers:
            containers = [
                a.parent
                for a in soup.find_all("a", href=re.compile(r"/jobs?/\d|/vacanc"))
            ]

        for item in containers:
            # Title link
            title_link = (
                item.find("a", href=re.compile(r"/jobs?/|/vacanc"))
                or item.find("h2", class_=True)
                or item.find("h3", class_=True)
            )
            if not title_link:
                continue

            if title_link.name == "a":
                title = title_link.get_text(strip=True)
                href = title_link.get("href", "")
            else:
                inner = title_link.find("a", href=True)
                if not inner:
                    continue
                title = inner.get_text(strip=True) or title_link.get_text(strip=True)
                href = inner.get("href", "")

            if not title or not href:
                continue
            url = href if href.startswith("http") else f"{BASE}{href}"
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Organisation
            org_el = item.find(class_=re.compile(r"company|employer|organisation|org", re.I))
            org = org_el.get_text(strip=True) if org_el else "Jobs in Brussels"

            # Location
            loc_el = item.find(class_=re.compile(r"locat|city|address", re.I))
            location = loc_el.get_text(strip=True) if loc_el else "Brussels"

            desc = f"{org} | {location}"

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
                )
            )

        return jobs

    def _has_next(self, soup: BeautifulSoup) -> bool:
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True).lower()
            if "next" in text or "›" in text or "»" in text:
                return True
        return False
