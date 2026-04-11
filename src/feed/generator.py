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
    # Brussels/EU categories
    "eu-institutions": "EU Institutions",
    "eu-affairs": "EU Affairs",
    "international-orgs": "International Organisations",
}

FEED_META: dict[str, dict[str, str]] = {
    "uk": {
        "government": "UK Government & Public Sector Jobs",
        "think-tanks": "UK Think Tank Jobs",
        "political-parties": "UK Political Party Jobs",
        "public-affairs": "UK Public Affairs & Lobbying Jobs",
        "ngos": "UK NGO & Charity Jobs",
        "fellowships": "UK Fellowships & Early Career Programmes",
        "trade-associations": "UK Trade Association Jobs",
        "general": "UK Political & Policy Jobs (General)",
    },
    "brussels": {
        "eu-institutions": "EU Institutions Jobs (Brussels)",
        "eu-affairs": "EU Affairs & Public Affairs Jobs (Brussels)",
        "think-tanks": "Brussels Think Tank Jobs",
        "ngos": "Brussels NGO Jobs",
        "fellowships": "EU Fellowships & Traineeships",
        "international-orgs": "International Organisation Jobs (Brussels/NATO)",
    },
}

# Which categories to generate per country
COUNTRY_CATEGORIES: dict[str, list[str]] = {
    "uk": [
        "government", "think-tanks", "political-parties", "public-affairs",
        "ngos", "fellowships", "trade-associations", "general",
    ],
    "brussels": [
        "eu-institutions", "eu-affairs", "think-tanks", "ngos",
        "fellowships", "international-orgs",
    ],
}


def generate_feeds(
    jobs: list[Job],
    output_dir: str,
    base_url: str = "",
    country: str = "uk",
) -> dict[str, int]:
    """Generate one RSS XML file per category. Returns {category: job_count}."""
    os.makedirs(output_dir, exist_ok=True)

    categories = COUNTRY_CATEGORIES.get(country, COUNTRY_CATEGORIES["uk"])
    feed_meta = FEED_META.get(country, FEED_META["uk"])

    by_category: dict[str, list[Job]] = {}
    for job in jobs:
        cat = job.category or "general"
        by_category.setdefault(cat, []).append(job)

    counts: dict[str, int] = {}
    for category in categories:
        cat_jobs = by_category.get(category, [])
        _write_feed(category, cat_jobs, output_dir, base_url, country=country, feed_meta=feed_meta)
        counts[category] = len(cat_jobs)
        log.info(f"Feed {country}-{category}.xml: {len(cat_jobs)} jobs")

    return counts


def _write_feed(
    category: str,
    jobs: list[Job],
    output_dir: str,
    base_url: str,
    country: str = "uk",
    feed_meta: dict[str, str] | None = None,
) -> None:
    label = CATEGORY_LABELS.get(category, category.title())
    if feed_meta is None:
        feed_meta = FEED_META.get(country, FEED_META["uk"])
    title = feed_meta.get(category, f"{country.title()} {label} Jobs")
    feed_url = f"{base_url}/{country}-{category}.xml" if base_url else f"/{country}-{category}.xml"

    # Cap at max items (already sorted newest-first from DB query)
    capped = jobs[:FEED_MAX_ITEMS]

    fg = FeedGenerator()
    fg.load_extension("dc")
    fg.id(feed_url)
    fg.title(title)
    fg.link(href=feed_url, rel="self")
    fg.language("en")
    fg.description(f"Job listings for {label} roles, scraped by Pol-Intel.")
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
        # Write organisation as dc:creator (plain text, RSS 2.0 compatible).
        # feedgen's fe.author() only works properly in Atom; in RSS it requires
        # an email address. dc:creator is the correct field for a plain-text
        # organisation name and is what the downstream Lovable parser reads.
        if job.organisation:
            fe.dc.dc_creator(job.organisation)

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

    out_path = os.path.join(output_dir, f"{country}-{category}.xml")
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
