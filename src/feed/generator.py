from __future__ import annotations

import json
import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from feedgen.feed import FeedGenerator

from src.models.job import Job

FEED_MAX_ITEMS = 500

log = logging.getLogger(__name__)

CATEGORY_LABELS = {
    "government": "Government",
    "think-tanks": "Think Tanks",
    "political-parties": "Political Parties",
    "public-affairs": "Public Affairs",
    "ngos": "NGOs",
    "fellowships": "Fellowships",
    "trade-associations": "Trade Associations",
    "general": "General",
}

FEED_META = {
    "government": "UK Government & Public Sector Jobs",
    "think-tanks": "UK Think Tank Jobs",
    "political-parties": "UK Political Party Jobs",
    "public-affairs": "UK Public Affairs & Lobbying Jobs",
    "ngos": "UK NGO & Charity Jobs",
    "fellowships": "UK Fellowships & Early Career Programmes",
    "trade-associations": "UK Trade Association Jobs",
    "general": "UK Political & Policy Jobs (General)",
}


def generate_feeds(jobs: list[Job], output_dir: str, base_url: str = "") -> dict[str, int]:
    """Generate one RSS XML file per category. Returns {category: job_count}."""
    os.makedirs(output_dir, exist_ok=True)

    by_category: dict[str, list[Job]] = {}
    for job in jobs:
        cat = job.category or "general"
        by_category.setdefault(cat, []).append(job)

    counts: dict[str, int] = {}
    for category in CATEGORY_LABELS:
        cat_jobs = by_category.get(category, [])
        _write_feed(category, cat_jobs, output_dir, base_url)
        counts[category] = len(cat_jobs)
        log.info(f"Feed uk-{category}.xml: {len(cat_jobs)} jobs")

    return counts


def _write_feed(category: str, jobs: list[Job], output_dir: str, base_url: str) -> None:
    label = CATEGORY_LABELS.get(category, category.title())
    title = FEED_META.get(category, f"UK {label} Jobs")
    feed_url = f"{base_url}/uk-{category}.xml" if base_url else f"/uk-{category}.xml"

    # Cap at max items (already sorted newest-first from DB query)
    capped = jobs[:FEED_MAX_ITEMS]

    fg = FeedGenerator()
    fg.id(feed_url)
    fg.title(title)
    fg.link(href=feed_url, rel="self")
    fg.language("en")
    fg.description(f"Job listings for UK {label} roles, scraped by Pol-Intel.")
    fg.lastBuildDate(datetime.now(timezone.utc))

    for job in capped:
        # Skip entries with non-absolute URLs
        if not job.url.startswith("http"):
            log.warning(f"Skipping job with non-absolute URL: {job.url!r}")
            continue

        fe = fg.add_entry()
        fe.id(job.guid)
        fe.title(job.title)
        fe.link(href=job.url)
        fe.description(job.description or "")
        fe.author({"name": job.organisation})

        # pubDate from date_scraped
        try:
            pub_dt = datetime.fromisoformat(job.date_scraped).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pub_dt = datetime.now(timezone.utc)
        fe.published(pub_dt)
        fe.updated(pub_dt)

        fe.category({"term": label})

        if job.closing_date:
            fe.summary(f"Closing: {job.closing_date}. {job.description or ''}"[:500])

    out_path = os.path.join(output_dir, f"uk-{category}.xml")
    fg.rss_file(out_path, pretty=True)

    # Validate the written XML parses cleanly
    try:
        ET.parse(out_path)
    except ET.ParseError as exc:
        log.error(f"Feed validation FAILED for {out_path}: {exc}")


def generate_status(
    output_dir: str,
    sources_checked: int = 0,
    sources_succeeded: int = 0,
    sources_failed: int = 0,
    failed_sources: list[str] | None = None,
    new_jobs_found: int = 0,
    total_active_jobs: int = 0,
    feeds_generated: int = 8,
) -> None:
    status = {
        "last_run": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_active_jobs": total_active_jobs,
        "sources_checked": sources_checked,
        "sources_succeeded": sources_succeeded,
        "sources_failed": sources_failed,
        "failed_sources": failed_sources or [],
        "new_jobs_found": new_jobs_found,
        "feeds_generated": feeds_generated,
    }
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "status.json"), "w") as f:
        json.dump(status, f, indent=2)
