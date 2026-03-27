"""
Third Sector Jobs scraper.

Portal: https://jp.thirdsector.co.uk/jobs/search
nopCommerce/.NET, fully server-rendered.
Pagination: ?pagenumber=N
Organisation and closing date fetched from detail pages (concurrent, semaphore-limited).
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from src.models.job import Job
from src.scrapers.base import BaseScraper, USER_AGENT, REQUEST_DELAY

BASE = "https://jp.thirdsector.co.uk"
SEARCH_URL = f"{BASE}/jobs/search"
MAX_PAGES = 20
DETAIL_CONCURRENCY = 5


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        stubs: list[dict] = []

        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            page = 1
            total_pages = 1

            while page <= min(total_pages, MAX_PAGES):
                url = SEARCH_URL if page == 1 else f"{SEARCH_URL}?pagenumber={page}"
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    await asyncio.sleep(REQUEST_DELAY)
                except httpx.HTTPError as e:
                    self.log.error(f"Page {page} error: {e}")
                    break

                soup = BeautifulSoup(r.text, "lxml")
                page_stubs, total_pages = self._parse_stubs(soup)
                stubs.extend(page_stubs)
                self.log.debug(f"Page {page}/{total_pages}: {len(page_stubs)} stubs")
                if not page_stubs:
                    break
                page += 1

            jobs = await self._enrich(client, stubs)

        self.log.info(f"Total: {len(jobs)} jobs")
        return jobs

    def _parse_stubs(self, soup: BeautifulSoup) -> tuple[list[dict], int]:
        stubs = []

        total_pages = 1
        for a in soup.select(".pager li a[data-page]"):
            dp = a.get("data-page", "")
            if dp.isdigit():
                total_pages = max(total_pages, int(dp))

        for div in soup.select("div.product-item.job-box"):
            title_el = div.select_one("h2.product-title a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            url = href if href.startswith("http") else f"{BASE}{href}"

            info_items = div.select("ul.job-info-list li p")
            location = info_items[0].get_text(strip=True) if info_items else None
            salary = info_items[1].get_text(strip=True) if len(info_items) > 1 else ""

            desc_el = div.select_one("div.description")
            desc = desc_el.get_text(strip=True) if desc_el else salary

            stubs.append({"title": title, "url": url, "location": location, "desc": desc})

        return stubs, total_pages

    async def _enrich(self, client: httpx.AsyncClient, stubs: list[dict]) -> list[Job]:
        sem = asyncio.Semaphore(DETAIL_CONCURRENCY)
        tasks = [self._fetch_detail(client, sem, stub) for stub in stubs]
        return [j for j in await asyncio.gather(*tasks) if j]

    async def _fetch_detail(
        self, client: httpx.AsyncClient, sem: asyncio.Semaphore, stub: dict
    ) -> Job | None:
        async with sem:
            org = "Third Sector"
            closing = None
            try:
                r = await client.get(stub["url"])
                r.raise_for_status()
                await asyncio.sleep(0.5)
                soup = BeautifulSoup(r.text, "lxml")

                org_el = soup.select_one("div.EmployerName a p, div.EmployerName p")
                if org_el:
                    org = org_el.get_text(strip=True)

                for label in soup.select("div.hours label"):
                    if "closing" in label.get_text(strip=True).lower():
                        p = label.find_next_sibling("p")
                        if p:
                            closing = self._parse_date(p.get_text(strip=True))
                        break
            except httpx.HTTPError as e:
                self.log.debug(f"Detail fetch failed {stub['url']}: {e}")

            desc_parts = [org]
            if stub.get("location"):
                desc_parts.append(stub["location"])
            if closing:
                desc_parts.append(f"Closes: {closing}")
            if stub.get("desc"):
                desc_parts.append(stub["desc"])
            desc = " | ".join(desc_parts)

            return Job(
                title=stub["title"],
                url=stub["url"],
                organisation=org,
                description=desc[:500],
                source_name=self.name,
                category=self.category,
                country=self.country,
                location=stub.get("location"),
                closing_date=closing,
            )

    @staticmethod
    def _parse_date(text: str) -> str | None:
        match = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", text)
        if match:
            try:
                day, month, year = match.groups()
                return datetime.strptime(f"{day} {month} {year}", "%d %B %Y").strftime("%Y-%m-%d")
            except ValueError:
                pass
        return None
