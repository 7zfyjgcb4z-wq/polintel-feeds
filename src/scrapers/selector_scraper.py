from __future__ import annotations

import logging
from typing import List
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from src.models.job import Job
from src.scrapers.base import USER_AGENT

log = logging.getLogger(__name__)


class SelectorScraper:
    async def scrape(self, url: str, selectors: dict, source_config: dict) -> List[Job]:
        if source_config.get("requires_js", False):
            log.warning(
                f"{source_config.get('name', url)}: requires_js=true but Playwright not enabled — skipping"
            )
            return []

        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
                timeout=30.0,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text
        except Exception as e:
            log.error(f"{source_config.get('name', url)}: fetch failed — {e}")
            return []

        return self._parse(html, url, selectors, source_config)

    def _parse(self, html: str, base_url: str, selectors: dict, source_config: dict) -> List[Job]:
        soup = BeautifulSoup(html, "lxml")
        org_static = source_config.get("org_static") or source_config.get("name", "")
        category = source_config.get("category", "general")
        country = source_config.get("country", "uk")
        source_name = source_config.get("name", "")

        card_sel = selectors.get("job_card")
        if not card_sel:
            log.warning(f"{source_name}: no job_card selector defined — skipping")
            return []

        cards = soup.select(card_sel)
        if not cards:
            log.info(f"{source_name}: no job cards found with selector '{card_sel}'")
            return []

        jobs: List[Job] = []
        for card in cards:
            title = self._extract(card, selectors.get("title"))
            if not title:
                continue

            link = self._extract_href(card, selectors.get("link"), base_url)
            if not link:
                continue

            org = self._extract(card, selectors.get("organisation")) or org_static
            location = self._extract(card, selectors.get("location"))
            closing_date = self._extract(card, selectors.get("closing_date"))

            jobs.append(Job(
                title=title,
                url=link,
                organisation=org,
                description="",
                source_name=source_name,
                category=category,
                country=country,
                location=location,
                closing_date=closing_date,
            ))

        return jobs

    @staticmethod
    def _extract(card, selector: str | None) -> str | None:
        if not selector:
            return None
        # Strip attribute portion like [href] for text extraction
        base_sel = selector.split("[")[0].strip()
        el = card.select_one(base_sel)
        if not el:
            return None
        text = el.get_text(strip=True)
        return text or None

    @staticmethod
    def _extract_href(card, selector: str | None, base_url: str) -> str | None:
        if not selector:
            # Fall back to first link in card
            el = card.find("a", href=True)
        else:
            base_sel = selector.split("[")[0].strip()
            el = card.select_one(base_sel)

        if not el:
            return None

        href = el.get("href", "")
        if not href:
            return None
        if href.startswith("http"):
            return href
        return urljoin(base_url, href)
