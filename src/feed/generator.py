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
    # Extended monitoring fields (all optional for backward compatibility)
    country: str = "uk",
    per_source: list[dict] | None = None,
    sources_disabled: int = 0,
    relevance_filtered: int = 0,
    descriptions_enriched: int = 0,
    run_duration_seconds: float = 0,
) -> None:
    status = {
        "last_run": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "country": country,
        "total_active_jobs": total_active_jobs,
        "new_jobs_found": new_jobs_found,
        "sources_checked": sources_checked,
        "sources_succeeded": sources_succeeded,
        "sources_failed": sources_failed,
        "sources_disabled": sources_disabled,
        "relevance_filtered": relevance_filtered,
        "descriptions_enriched": descriptions_enriched,
        "feeds_generated": feeds_generated,
        "run_duration_seconds": run_duration_seconds,
        "failed_sources": failed_sources or [],
        "per_source": per_source or [],
    }
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "status.json"), "w") as f:
        json.dump(status, f, indent=2)


def generate_alerts(
    output_dir: str,
    current_per_source: list[dict],
    previous_status_path: str,
    previous_alerts_path: str,
) -> None:
    """Compare current vs previous run to detect zero-result and failure regressions.

    Reads the OLD status.json and alerts.json before they are overwritten, so this
    must be called BEFORE generate_status().
    """
    # Load previous per-source data
    prev_by_source: dict[str, dict] = {}
    try:
        with open(previous_status_path) as f:
            prev_status = json.load(f)
        for entry in prev_status.get("per_source", []):
            prev_by_source[entry["name"]] = entry
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass  # first run or legacy status.json — no baseline to compare against

    # Load previous alerts for consecutive-count tracking
    prev_alerts_by_source: dict[str, dict] = {}
    prev_tracking: dict[str, dict] = {}
    try:
        with open(previous_alerts_path) as f:
            prev_alerts_data = json.load(f)
        for alert in prev_alerts_data.get("alerts", []):
            prev_alerts_by_source[alert["source"]] = alert
        prev_tracking = prev_alerts_data.get("_tracking", {})
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    alerts: list[dict] = []
    tracking_out: dict[str, dict] = {"consecutive_failures": {}}

    for entry in current_per_source:
        name = entry["name"]
        current_found = entry.get("jobs_found", 0)
        current_status = entry.get("status", "success")
        prev = prev_by_source.get(name, {})
        prev_found = prev.get("jobs_found")  # None if source is new this run

        # ── Zero-result detection ──────────────────────────────────────────────
        if current_status == "success" and current_found == 0:
            prev_zero_alert = prev_alerts_by_source.get(name, {})
            had_zero_alert = prev_zero_alert.get("type") == "zero_result_after_success"

            if prev_found is not None and prev_found > 0:
                # First zero run
                alerts.append({
                    "source": name,
                    "type": "zero_result_after_success",
                    "previous_count": prev_found,
                    "current_count": 0,
                    "consecutive_zeros": 1,
                    "message": (
                        f"{name} returned 0 jobs after previously returning {prev_found}. "
                        "May be broken selector, site redesign, or no current vacancies."
                    ),
                })
            elif had_zero_alert:
                # Continuing zero — increment counter
                consecutive = prev_zero_alert.get("consecutive_zeros", 0) + 1
                original_count = prev_zero_alert.get("previous_count", 0)
                alerts.append({
                    "source": name,
                    "type": "zero_result_after_success",
                    "previous_count": original_count,
                    "current_count": 0,
                    "consecutive_zeros": consecutive,
                    "message": (
                        f"{name} returned 0 jobs (was {original_count}) for "
                        f"{consecutive} consecutive run(s). Review selector or check for vacancies."
                    ),
                })

        # ── Consecutive failure detection ──────────────────────────────────────
        prev_fail_counts = prev_tracking.get("consecutive_failures", {})
        if current_status == "failed":
            prev_count = prev_fail_counts.get(name, 0)
            new_count = prev_count + 1
            tracking_out["consecutive_failures"][name] = new_count
            if new_count >= 3:
                alerts.append({
                    "source": name,
                    "type": "consecutive_failure",
                    "consecutive_failures": new_count,
                    "message": f"{name} has failed for {new_count} consecutive pipeline runs.",
                })
        else:
            tracking_out["consecutive_failures"][name] = 0  # reset on success

    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "alerts": alerts,
        "_tracking": tracking_out,
    }
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "alerts.json"), "w") as f:
        json.dump(output, f, indent=2)

    if alerts:
        log.warning(f"Health alerts: {len(alerts)} issue(s) detected — see feeds/alerts.json")
    else:
        log.info("Health check: no alerts.")
