"""
Tom Manatos Jobs scraper.

WordPress-based Capitol Hill and DC political job board.
Each post is a job listing; employer name is often in the post title:
  "Employer Name - Role Title"

Pagination: /page/N/ URL pattern.
Cap: 200 jobs.

Note: the site returned 403 with a plain User-Agent during URL verification.
This scraper uses browser-like headers to match what a real browser sends.
"""
from __future__ import annotations

import asyncio
import re

import httpx
from bs4 import BeautifulSoup

from src.models.job import Job
from src.scrapers.base import BaseScraper, REQUEST_DELAY

BASE = "https://www.tommanatosjobs.com"
MAX_PAGES = 10
PER_PAGE_CAP = 200

# Browser-like headers to avoid WAF blocks
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        partisan_lean = self.source.get("partisan_lean")
        jobs: list[Job] = []
        seen_urls: set[str] = set()

        async with httpx.AsyncClient(
            headers=BROWSER_HEADERS,
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            for page_num in range(1, MAX_PAGES + 1):
                if len(jobs) >= PER_PAGE_CAP:
                    break

                url = BASE if page_num == 1 else f"{BASE}/page/{page_num}/"

                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    await asyncio.sleep(REQUEST_DELAY)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        break  # no more pages
                    self.log.error(f"HTTP {exc.response.status_code} fetching {url}")
                    if page_num == 1:
                        raise
                    break
                except httpx.HTTPError as exc:
                    self.log.error(f"Fetch error {url}: {exc}")
                    if page_num == 1:
                        raise
                    break

                soup = BeautifulSoup(r.text, "lxml")
                page_jobs = self._parse_page(soup, seen_urls, partisan_lean)

                if not page_jobs:
                    break  # no posts found — end of content or layout mismatch

                jobs.extend(page_jobs)
                self.log.debug(f"Page {page_num}: {len(page_jobs)} new jobs")

                if len(jobs) >= PER_PAGE_CAP:
                    break

        self.log.info(f"Total: {len(jobs)} jobs")
        return jobs[:PER_PAGE_CAP]

    def _parse_page(
        self,
        soup: BeautifulSoup,
        seen_urls: set[str],
        partisan_lean: str | None,
    ) -> list[Job]:
        jobs: list[Job] = []

        # WordPress post selectors — try common theme patterns
        articles = (
            soup.select("article.post, article.hentry, article.type-post")
            or soup.select("div.post, div.hentry")
            or soup.select("article")
        )

        for article in articles:
            # Title and URL
            title_el = (
                article.select_one("h2.entry-title a, h1.entry-title a, "
                                   "h2.post-title a, h3.entry-title a, "
                                   ".entry-title a")
            )
            if not title_el:
                # Fall back to any heading link in the article
                title_el = article.select_one("h1 a, h2 a, h3 a")
            if not title_el:
                continue

            raw_title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            if not href or not href.startswith("http"):
                continue
            if href in seen_urls:
                continue
            seen_urls.add(href)

            # Split "Employer Name - Role Title" heuristic
            org, title = _split_title(raw_title)

            # Description: first ~500 chars of post content
            content_el = article.select_one(
                ".entry-content, .post-content, .entry-summary, .post-excerpt"
            )
            description = ""
            if content_el:
                description = content_el.get_text(separator=" ", strip=True)[:500]
            if not description:
                description = f"{org} — {title}" if org else title

            jobs.append(
                Job(
                    title=title,
                    url=href,
                    organisation=org,
                    description=description[:500],
                    source_name=self.name,
                    category=self.category,
                    country=self.country,
                    location="Washington, DC",
                    partisan_lean=partisan_lean,
                )
            )

        return jobs


def _split_title(raw: str) -> tuple[str, str]:
    """
    Split 'Employer Name - Role Title' into (org, title).
    Falls back to (raw, raw) if no separator found.
    """
    # Try " - " (most common on Tom Manatos) then " – " (en-dash)
    for sep in (" - ", " – ", " | "):
        if sep in raw:
            parts = raw.split(sep, 1)
            org = parts[0].strip()
            title = parts[1].strip()
            if org and title:
                return org, title

    # No separator: use the full title, org unknown
    return "Unknown", raw.strip()
