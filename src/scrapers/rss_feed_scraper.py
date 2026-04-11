from __future__ import annotations

import logging
import re
from typing import List

import feedparser
from bs4 import BeautifulSoup

from src.models.job import Job

log = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_PIPE_META_RE = re.compile(r"^[^|]+\|[^|]+\|")  # 3+ pipe-separated segments


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = _HTML_TAG_RE.sub(" ", text)
    return " ".join(text.split())


def _is_thin_description(text: str) -> bool:
    if not text or len(text) < 200:
        return True
    if _PIPE_META_RE.search(text):
        return True
    return False


class RSSFeedScraper:
    async def scrape(self, url: str, field_map: dict, source_config: dict) -> List[Job]:
        org_static = source_config.get("org_static")
        category = source_config.get("category", "general")
        country = source_config.get("country", "uk")
        source_name = source_config.get("name", "")

        try:
            feed = feedparser.parse(url)
        except Exception as e:
            log.error(f"{source_name}: feedparser error — {e}")
            return []

        if feed.bozo and not feed.entries:
            log.warning(f"{source_name}: feed parse error — {feed.bozo_exception}")
            return []

        jobs: List[Job] = []
        for entry in feed.entries:
            title = self._get_field(entry, field_map, "title")
            if not title:
                continue

            link = self._get_field(entry, field_map, "link") or getattr(entry, "link", None)
            if not link or not link.startswith("http"):
                continue

            # Organisation
            org = org_static
            if not org:
                org_field = field_map.get("organisation")
                if org_field:
                    raw_org = getattr(entry, org_field, None)
                    if raw_org and "@" not in raw_org:
                        org = raw_org
            if not org:
                org = source_name

            # Location
            location = None
            loc_field = field_map.get("location")
            if loc_field:
                raw_loc = getattr(entry, loc_field, None)
                if isinstance(raw_loc, list) and raw_loc:
                    location = raw_loc[0].get("term") if isinstance(raw_loc[0], dict) else str(raw_loc[0])
                elif raw_loc:
                    location = str(raw_loc)

            # Description — prefer longer of summary vs content[0]
            desc_field = field_map.get("description", "description")
            summary = _strip_html(getattr(entry, "summary", "") or "")
            content = ""
            if hasattr(entry, "content") and entry.content:
                content = _strip_html(entry.content[0].get("value", ""))
            description = content if len(content) > len(summary) else summary

            # Date
            pub_date = None
            date_field = field_map.get("date", "published")
            if hasattr(entry, date_field):
                pub_date = getattr(entry, date_field, None)

            needs_enrichment = _is_thin_description(description)

            j = Job(
                title=title,
                url=link,
                organisation=org,
                description=description,
                source_name=source_name,
                category=category,
                country=country,
                location=location,
            )
            # Tag thin descriptions for downstream enrichment
            j._needs_enrichment = needs_enrichment  # type: ignore[attr-defined]
            jobs.append(j)

        log.info(f"{source_name}: {len(jobs)} entries from RSS feed")
        return jobs

    @staticmethod
    def _get_field(entry, field_map: dict, logical_name: str) -> str | None:
        rss_field = field_map.get(logical_name, logical_name)
        val = getattr(entry, rss_field, None)
        if val is None:
            val = getattr(entry, logical_name, None)
        if isinstance(val, str):
            return val.strip() or None
        return None
