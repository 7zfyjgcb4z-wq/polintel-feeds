from __future__ import annotations

import glob
import json
import logging
import os
import re
import sqlite3
import statistics
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from feedgen.feed import FeedGenerator

from src.models.job import Job


log = logging.getLogger(__name__)


def _xml_safe(text: str | None) -> str | None:
    if text is None:
        return None
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

POLINTEL_NS = "https://pol-intel.com/rss-ext/1.0"

# Register RSS-related namespaces so ET preserves prefixes when re-serialising
# a feedgen-generated file (otherwise ET emits ns0:, ns1: etc.)
ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
ET.register_namespace("dc", "http://purl.org/dc/elements/1.1/")
ET.register_namespace("polintel", POLINTEL_NS)

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
    # US categories
    "us-congress": "US Congress",
    "us-think-tanks": "US Think Tanks",
    "us-government-affairs": "US Government Affairs",
    "us-ngos": "US NGOs & Advocacy",
    "us-fellowships": "US Fellowships",
    "us-campaigns": "US Campaigns & Parties",
    # EU national categories
    "national-politics": "National Politics",
    "foundations": "Political Foundations",
    # Internship / graduate pipeline categories
    "research": "Research & Polling",
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
    "us": {
        "us-congress": "US Congress & Capitol Hill Jobs",
        "us-think-tanks": "US Think Tank Jobs",
        "us-government-affairs": "US Government Affairs & Lobbying Jobs",
        "us-ngos": "US NGO & Advocacy Jobs",
        "us-fellowships": "US Policy Fellowships",
        "us-campaigns": "US Campaigns & Political Party Jobs",
    },
    # EU national regions
    "dach": {
        "national-politics": "DACH National Politics Jobs (DE/AT)",
        "public-affairs": "DACH Public Affairs Jobs (DE/AT)",
        "think-tanks": "DACH Think Tank Jobs (DE/AT)",
        "foundations": "German & Austrian Political Foundation Jobs",
        "political-parties": "DACH Political Party Jobs (DE/AT)",
        "trade-associations": "DACH Trade Association Jobs (DE/AT)",
    },
    "southern": {
        "national-politics": "Southern Europe National Politics Jobs (FR/ES/IT/PT/GR)",
        "think-tanks": "Southern Europe Think Tank Jobs (FR/ES/IT/PT/GR)",
        "political-parties": "Southern Europe Political Party Jobs (FR/ES/IT)",
        "public-affairs": "Southern Europe Public Affairs Jobs (FR/ES/IT)",
        "trade-associations": "Southern Europe Trade Association Jobs (FR/ES/IT)",
    },
    "benelux": {
        "political-parties": "Benelux Political Party Jobs (NL)",
        "national-politics": "Benelux National Politics Jobs (NL)",
        "think-tanks": "Benelux Think Tank Jobs (NL)",
    },
    "nordics": {
        "think-tanks": "Nordic Think Tank Jobs (SE/DK/FI/NO)",
        "national-politics": "Nordic National Politics Jobs (SE/DK/FI)",
    },
    "cee": {
        "think-tanks": "CEE Think Tank Jobs (IE/PL/CZ)",
        "national-politics": "CEE National Politics Jobs (IE/PL/CZ)",
    },
    "pan-eu": {
        "eu-affairs": "Pan-European EU Affairs Jobs",
        "international-orgs": "Pan-European International Organisation Jobs",
    },
    "internship_graduate": {
        "public-affairs": "Internship & Graduate — Public Affairs & Lobbying",
        "research": "Internship & Graduate — Research & Polling",
        "international-orgs": "Internship & Graduate — International Organisations",
        "us-fellowships": "Internship & Graduate — US Fellowships",
        "us-campaigns": "Internship & Graduate — US Campaigns",
        "us-congress": "Internship & Graduate — US Congress",
        "general": "Internship & Graduate — General",
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
    "us": [
        "us-congress", "us-think-tanks", "us-government-affairs",
        "us-ngos", "us-fellowships", "us-campaigns",
    ],
    # EU national regions
    "dach": [
        "national-politics", "public-affairs", "think-tanks",
        "foundations", "political-parties", "trade-associations",
    ],
    "southern": [
        "national-politics", "think-tanks", "political-parties",
        "public-affairs", "trade-associations",
    ],
    "benelux": ["political-parties", "national-politics", "think-tanks"],
    "nordics": ["think-tanks", "national-politics"],
    "cee": ["think-tanks", "national-politics"],
    "pan-eu": ["eu-affairs", "international-orgs"],
    "internship_graduate": [
        "public-affairs", "research", "international-orgs",
        "us-fellowships", "us-campaigns", "us-congress", "general",
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


def _inject_location(out_path: str, jobs: list[Job]) -> None:
    """Post-process an RSS file to add <polintel:location> to job items.

    Only modifies the file when at least one job has a non-empty location.
    Matches items by <guid> text, which is always job.url.
    """
    location_by_url = {
        job.url: job.location
        for job in jobs
        if job.location and job.location.strip()
    }
    if not location_by_url:
        return

    tree = ET.parse(out_path)
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        return

    modified = False
    for item in channel.findall("item"):
        guid_el = item.find("guid")
        if guid_el is None or not guid_el.text:
            continue
        loc = location_by_url.get(guid_el.text.strip())
        if loc:
            el = ET.SubElement(item, f"{{{POLINTEL_NS}}}location")
            el.text = loc
            modified = True

    if modified:
        tree.write(out_path, encoding="UTF-8", xml_declaration=True)


def _inject_partisan_lean(out_path: str, jobs: list[Job]) -> None:
    """Post-process an RSS file to add <polintel:partisanLean> to US job items.

    Only modifies the file when at least one job in the feed has partisan_lean set.
    UK and Brussels feeds are untouched (no jobs have the field populated).
    Matches items by <guid> text, which is always job.url.
    """
    lean_by_url = {
        job.url: job.partisan_lean
        for job in jobs
        if job.partisan_lean is not None
    }
    if not lean_by_url:
        return

    tree = ET.parse(out_path)
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        return

    modified = False
    for item in channel.findall("item"):
        guid_el = item.find("guid")
        if guid_el is None or not guid_el.text:
            continue
        lean = lean_by_url.get(guid_el.text.strip())
        if lean:
            el = ET.SubElement(item, f"{{{POLINTEL_NS}}}partisanLean")
            el.text = lean
            modified = True

    if modified:
        tree.write(out_path, encoding="UTF-8", xml_declaration=True)


def _inject_contract_fields(out_path: str, jobs: list[Job]) -> None:
    """Add <polintel:closingDate> and <polintel:descriptionSource> to items, matched by <guid>."""
    by_url = {
        job.url: (job.closing_date, job.description_source)
        for job in jobs
        if (job.closing_date and job.closing_date.strip()) or job.description_source
    }
    if not by_url:
        return
    tree = ET.parse(out_path)
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        return
    modified = False
    for item in channel.findall("item"):
        guid_el = item.find("guid")
        if guid_el is None or not guid_el.text:
            continue
        vals = by_url.get(guid_el.text.strip())
        if not vals:
            continue
        closing, dsource = vals
        if closing and closing.strip():
            el = ET.SubElement(item, f"{{{POLINTEL_NS}}}closingDate")
            el.text = closing.strip()[:10]
            modified = True
        if dsource:
            el = ET.SubElement(item, f"{{{POLINTEL_NS}}}descriptionSource")
            el.text = dsource
            modified = True
    if modified:
        tree.write(out_path, encoding="UTF-8", xml_declaration=True)


def _ensure_description_element(out_path: str) -> None:
    """feedgen omits <description> entirely when the body is an empty string
    (falsy-check in its own serialiser). The empty-description transport
    guarantee requires every item to carry the element regardless, so
    ingestion can distinguish 'no body' from 'item missing'."""
    tree = ET.parse(out_path)
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        return
    modified = False
    for item in channel.findall("item"):
        if item.find("description") is None:
            el = ET.SubElement(item, "description")
            el.text = ""
            modified = True
    if modified:
        tree.write(out_path, encoding="UTF-8", xml_declaration=True)


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

    fg = FeedGenerator()
    fg.load_extension("dc")
    fg.id(feed_url)
    fg.title(title)
    fg.link(href=feed_url, rel="self")
    fg.language("en")
    fg.description(f"Job listings for {label} roles, scraped by Pol-Intel.")
    fg.lastBuildDate(datetime.now(timezone.utc))

    for job in jobs:
        # Skip entries with non-absolute URLs
        if not job.url.startswith("http"):
            log.warning(f"Skipping job with non-absolute URL: {job.url!r}")
            continue

        fe = fg.add_entry()
        fe.id(job.guid)
        fe.title(_xml_safe(job.title))
        fe.link(href=job.url)
        body = _xml_safe(job.description) or ""
        if len(body) > 10000:
            cut = body.rfind(" ", 0, 10000)
            body = body[: cut if cut > 0 else 10000]
        fe.description(body)
        # Write organisation as dc:creator (plain text, RSS 2.0 compatible).
        # feedgen's fe.author() only works properly in Atom; in RSS it requires
        # an email address. dc:creator is the correct field for a plain-text
        # organisation name and is what the downstream Lovable parser reads.
        if job.organisation:
            fe.dc.dc_creator(_xml_safe(job.organisation))

        # pubDate ONLY when a real posted date exists. Never fall back to scrape
        # time or now(): an absent date must stay absent (ingestion stores null).
        # Date-only values emit as midnight UTC ("date known, time unknown").
        if job.posted_date:
            try:
                pub_dt = datetime.fromisoformat(job.posted_date)
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                fe.published(pub_dt)
                fe.updated(pub_dt)
            except (ValueError, TypeError):
                pass  # unparseable date: emit nothing rather than a fabricated value

        fe.category({"term": label})

    out_path = os.path.join(output_dir, f"{country}-{category}.xml")
    fg.rss_file(out_path, pretty=True)

    # Guarantee: every item carries a <description> element, even when empty
    _ensure_description_element(out_path)

    # Inject <polintel:location> when the extractor has populated job.location
    _inject_location(out_path, jobs)

    # Inject <polintel:partisanLean> for US jobs (no-op for UK/Brussels)
    _inject_partisan_lean(out_path, jobs)

    # Inject <polintel:closingDate> and <polintel:descriptionSource>
    _inject_contract_fields(out_path, jobs)

    # Validate the written XML parses cleanly (checks final output, post-injection)
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
    # Backward-compatible aggregate: always written.
    with open(os.path.join(output_dir, "status.json"), "w") as f:
        json.dump(status, f, indent=2)
    # Per-country baseline: skip when this was a regenerate-only run (no sources
    # checked) so we do not overwrite a real baseline with an empty one.
    if sources_checked > 0:
        country_path = os.path.join(output_dir, f"status-{country}.json")
        with open(country_path, "w") as f:
            json.dump(status, f, indent=2)


def generate_alerts(
    output_dir: str,
    current_per_source: list[dict],
    previous_status_path: str,
    previous_alerts_path: str,
    country: str = "uk",
) -> None:
    """Compare current vs previous run to detect zero-result and failure regressions.

    Reads the per-country status baseline (status-<country>.json) before it is
    overwritten, so this must be called BEFORE generate_status(). For backward
    compatibility the old previous_status_path/previous_alerts_path parameters
    remain but are ignored in favour of the per-country paths.
    """
    # Per-country baseline: compare like with like (UK vs UK, US vs US).
    country_status_path = os.path.join(output_dir, f"status-{country}.json")
    country_alerts_path = os.path.join(output_dir, f"alerts-{country}.json")

    # Load previous per-source data from the country-specific baseline.
    prev_by_source: dict[str, dict] = {}
    try:
        with open(country_status_path) as f:
            prev_status = json.load(f)
        for entry in prev_status.get("per_source", []):
            prev_by_source[entry["name"]] = entry
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass  # first run for this country; no baseline to compare against

    # Load previous country-level alerts for consecutive-count tracking.
    prev_alerts_by_source: dict[str, dict] = {}
    prev_tracking: dict[str, dict] = {}
    try:
        with open(country_alerts_path) as f:
            prev_alerts_data = json.load(f)
        for alert in prev_alerts_data.get("alerts", []):
            prev_alerts_by_source[alert["source"]] = alert
        prev_tracking = prev_alerts_data.get("_tracking", {})
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    alerts: list[dict] = []
    tracking_out: dict[str, dict] = {"consecutive_failures": {}}

    current_month = datetime.now(timezone.utc).month

    for entry in current_per_source:
        name = entry["name"]
        current_found = entry.get("jobs_found", 0)
        current_status = entry.get("status", "success")
        prev = prev_by_source.get(name, {})
        prev_found = prev.get("jobs_found")  # None if source is new this run

        # ── Cyclical source: suppress zero-result alerts outside active window ─
        # Sources with cyclical: true have legitimate empty periods (e.g. Schuman
        # traineeships, Blue Book, Fast Stream). A zero result outside the configured
        # active months is a healthy state, not a failure.
        is_cyclical = entry.get("cyclical", False)
        active_months = entry.get("cyclical_active_months")  # list[int] or None
        in_window = (not active_months) or (current_month in active_months)

        # ── Zero-result detection ──────────────────────────────────────────────
        if current_status == "success" and current_found == 0:
            if is_cyclical and not in_window:
                # Off-season zero result is healthy — silently reset any prior alert
                # (do not carry forward a zero_result alert from a previous cycle)
                pass
            else:
                prev_zero_alert = prev_alerts_by_source.get(name, {})
                had_zero_alert = prev_zero_alert.get("type") == "zero_result_after_success"

                if prev_found is not None and prev_found > 0:
                    # First zero run (inside window or non-cyclical)
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

        # ── Upstream staleness detection ───────────────────────────────────────
        # Scrapers that consume third-party maintained upstream sources (e.g.
        # dwillis/house-jobs) set upstream_stale: true in their per-source
        # results when the upstream hasn't been updated within the expected cadence.
        if entry.get("upstream_stale"):
            last_update = entry.get("upstream_last_bulletin", "unknown")
            days = entry.get("upstream_days_since_update")
            days_str = f"{days} days" if days is not None else "unknown days"
            alerts.append({
                "source": name,
                "type": "upstream_stale",
                "upstream_last_bulletin": last_update,
                "upstream_days_since_update": days,
                "message": (
                    f"{name} upstream data source has not been updated in {days_str} "
                    f"(last bulletin: {last_update}). "
                    "Verify dwillis/house-jobs is still being maintained."
                ),
            })

    # Shape-mismatch events emitted by ATS extractors during this run.
    # Imported lazily to avoid coupling the feed module to scraper internals at
    # module load time; the try/except ensures a missing import never silences
    # the existing alerts.
    try:
        from src.scrapers.ats_extractors.api_extractors import drain_shape_events  # noqa: PLC0415
        for event in drain_shape_events():
            alerts.append({
                "source": event["source"],
                "type": "shape_mismatch",
                "platform": event["platform"],
                "identifier": event["identifier"],
                "raw_count": event["raw_count"],
                "yield_count": event["yield_count"],
                "message": event["message"],
            })
    except Exception as _exc:
        log.debug("Shape event drain failed (non-fatal): %s", _exc)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    output = {
        "generated_at": generated_at,
        "country": country,
        "alerts": alerts,
        "_tracking": tracking_out,
    }
    os.makedirs(output_dir, exist_ok=True)

    # Write per-country alerts file.
    with open(country_alerts_path, "w") as f:
        json.dump(output, f, indent=2)

    # Rebuild merged alerts.json from every alerts-*.json present on disk.
    merged_alerts: list[dict] = []
    for path in sorted(glob.glob(os.path.join(output_dir, "alerts-*.json"))):
        try:
            with open(path) as f:
                data = json.load(f)
            merged_alerts.extend(data.get("alerts", []))
        except (json.JSONDecodeError, OSError):
            pass
    merged_output = {
        "generated_at": generated_at,
        "alerts": merged_alerts,
    }
    with open(os.path.join(output_dir, "alerts.json"), "w") as f:
        json.dump(merged_output, f, indent=2)

    if alerts:
        log.warning(f"Health alerts: {len(alerts)} issue(s) detected; see feeds/alerts-{country}.json")
    else:
        log.info("Health check: no alerts.")


# ---------------------------------------------------------------------------
# generate_health
# ---------------------------------------------------------------------------

# Mapping from country key to the YAML config file holding its sources.
# Kept in sync with COUNTRY_CONFIG in pipeline.py.
_CONFIG_DIR = Path(__file__).parent.parent / "config"
_COUNTRY_CONFIG: dict[str, Path] = {
    "uk": _CONFIG_DIR / "sources.yaml",
    "brussels": _CONFIG_DIR / "sources-brussels.yaml",
    "us": _CONFIG_DIR / "sources-us.yaml",
    "dach": _CONFIG_DIR / "sources-dach.yaml",
    "southern": _CONFIG_DIR / "sources-southern.yaml",
    "benelux": _CONFIG_DIR / "sources-benelux.yaml",
    "nordics": _CONFIG_DIR / "sources-nordics.yaml",
    "cee": _CONFIG_DIR / "sources-cee.yaml",
    "pan-eu": _CONFIG_DIR / "sources-pan-eu.yaml",
    "internship_graduate": _CONFIG_DIR / "sources-internship-graduate.yaml",
}


def _load_all_sources() -> list[dict]:
    """Load sources from all country YAML configs with `country_key` injected."""
    all_sources: list[dict] = []
    for country_key, path in _COUNTRY_CONFIG.items():
        try:
            with open(path) as f:
                config = yaml.safe_load(f)
            for s in config.get("sources", []):
                s = dict(s)
                s["_country_key"] = country_key
                all_sources.append(s)
        except (FileNotFoundError, Exception) as exc:
            log.warning("generate_health: could not load %s: %s", path, exc)
    return all_sources


def _count_xml_items(feed_path: str) -> int:
    """Count <item> elements in an RSS XML file. Returns 0 on any error."""
    try:
        tree = ET.parse(feed_path)
        channel = tree.getroot().find("channel")
        if channel is None:
            return 0
        return len(channel.findall("item"))
    except Exception:
        return 0


def _extract_links(feed_path: str) -> list[str]:
    """Return all <link> texts from <item> elements in an RSS file."""
    links: list[str] = []
    try:
        tree = ET.parse(feed_path)
        channel = tree.getroot().find("channel")
        if channel is None:
            return links
        for item in channel.findall("item"):
            link_el = item.find("link")
            if link_el is not None and link_el.text:
                links.append(link_el.text.strip())
    except Exception:
        pass
    return links


def _bare_path(url: str) -> str:
    """Return scheme + host + path of a URL, stripping query and fragment."""
    try:
        from urllib.parse import urlparse  # noqa: PLC0415
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}{p.path}"
    except Exception:
        return url


def _load_status_files(output_dir: str) -> dict[str, dict]:
    """Load all status-<country>.json files, keyed by country."""
    statuses: dict[str, dict] = {}
    for path in glob.glob(os.path.join(output_dir, "status-*.json")):
        fname = os.path.basename(path)
        # status-<country>.json -> country = fname[7:-5]
        ckey = fname[7:-5]
        try:
            with open(path) as f:
                statuses[ckey] = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return statuses


def _load_previous_health(output_dir: str) -> dict[str, dict]:
    """Load previous health.json and index sources by name for carry-forward."""
    prev_by_name: dict[str, dict] = {}
    try:
        with open(os.path.join(output_dir, "health.json")) as f:
            prev = json.load(f)
        for s in prev.get("sources", []):
            if "name" in s:
                prev_by_name[s["name"]] = s
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return prev_by_name


def _db_stats_per_source(db_path: str) -> dict[str, dict]:
    """Query jobs.db for per-source health metrics. Returns {} on any error."""
    stats: dict[str, dict] = {}
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        now = datetime.now(timezone.utc)
        t7 = (now - timedelta(days=7)).isoformat()
        t28 = (now - timedelta(days=28)).isoformat()
        t56 = (now - timedelta(days=56)).isoformat()
        t3 = (now - timedelta(days=3)).isoformat()

        # Active row counts
        for row in conn.execute(
            "SELECT source_name, COUNT(*) AS n FROM jobs WHERE is_active=1 GROUP BY source_name"
        ):
            stats.setdefault(row["source_name"], {})["active_rows"] = row["n"]

        # new_7d
        for row in conn.execute(
            "SELECT source_name, COUNT(*) AS n FROM jobs WHERE date_first_seen >= ? GROUP BY source_name",
            (t7,),
        ):
            stats.setdefault(row["source_name"], {})["new_7d"] = row["n"]

        # new_28d
        for row in conn.execute(
            "SELECT source_name, COUNT(*) AS n FROM jobs WHERE date_first_seen >= ? GROUP BY source_name",
            (t28,),
        ):
            stats.setdefault(row["source_name"], {})["new_28d"] = row["n"]

        # new_prev_28d (first seen in the 28-56 day window)
        for row in conn.execute(
            "SELECT source_name, COUNT(*) AS n FROM jobs WHERE date_first_seen >= ? AND date_first_seen < ? GROUP BY source_name",
            (t56, t28),
        ):
            stats.setdefault(row["source_name"], {})["new_prev_28d"] = row["n"]

        # stub_share
        for row in conn.execute(
            "SELECT source_name, COUNT(*) AS n FROM jobs WHERE is_active=1 AND description_source='stub' GROUP BY source_name"
        ):
            sn = row["source_name"]
            stub_n = row["n"]
            active = stats.get(sn, {}).get("active_rows", 0)
            stats.setdefault(sn, {})["stub_share"] = round(stub_n / active, 4) if active else 0.0

        # median_lifetime_days: rows first seen in last 28 days
        lifetimes_by_source: dict[str, list[float]] = {}
        for row in conn.execute(
            """SELECT source_name, date_first_seen, date_last_seen
               FROM jobs WHERE date_first_seen >= ?""",
            (t28,),
        ):
            try:
                d0 = datetime.fromisoformat(row["date_first_seen"].replace("Z", "+00:00"))
                d1 = datetime.fromisoformat(row["date_last_seen"].replace("Z", "+00:00"))
                lifetimes_by_source.setdefault(row["source_name"], []).append(
                    (d1 - d0).total_seconds() / 86400
                )
            except (ValueError, AttributeError):
                pass
        for sn, days in lifetimes_by_source.items():
            stats.setdefault(sn, {})["median_lifetime_days"] = round(statistics.median(days), 2)

        # closing_soon_share: share of active rows that close within 3 days of date_first_seen
        for row in conn.execute(
            """SELECT source_name, COUNT(*) AS total,
               SUM(CASE WHEN closing_date IS NOT NULL
                    AND closing_date <= datetime(date_first_seen, '+3 days')
                    THEN 1 ELSE 0 END) AS fast_close
               FROM jobs WHERE is_active=1
               GROUP BY source_name"""
        ):
            sn = row["source_name"]
            total = row["total"] or 0
            fast = row["fast_close"] or 0
            stats.setdefault(sn, {})["closing_soon_share"] = round(fast / total, 4) if total else 0.0

        conn.close()
    except Exception as exc:
        log.warning("generate_health: DB stats query failed: %s", exc)
    return stats


def _compute_status_enum(
    *,
    enabled: bool,
    last_success_at: str | None,
    new_7d: int | None,
    new_28d: int | None,
    new_prev_28d: int | None,
    consecutive_zero_runs: int,
    is_cyclical: bool,
    last_run_failed: bool,
    is_intl_graduate: bool,
) -> str:
    if not enabled:
        return "off"
    if is_intl_graduate:
        # No DB rows by design; can only check run success.
        if last_run_failed and last_success_at is None:
            return "dead"
        return "healthy"
    # Check dead: last success older than 7 days, or 3+ consecutive zeros (non-cyclical)
    now = datetime.now(timezone.utc)
    if last_success_at is not None:
        try:
            ls = datetime.fromisoformat(last_success_at.replace("Z", "+00:00"))
            if (now - ls).total_seconds() > 7 * 86400:
                return "dead"
        except (ValueError, AttributeError):
            pass
    if not is_cyclical and consecutive_zero_runs >= 3:
        return "dead"
    # Declining: new_28d < half of new_prev_28d, provided prev period was substantial
    if (
        new_28d is not None
        and new_prev_28d is not None
        and new_prev_28d >= 20
        and new_28d < 0.5 * new_prev_28d
    ):
        return "declining"
    # Stale: no new rows in 7 days but last run succeeded
    if new_7d == 0 and not last_run_failed:
        return "stale"
    return "healthy"


def generate_health(output_dir: str, db_path: str) -> None:
    """Produce feeds/health.json from status-*.json files and jobs.db.

    Aggregates per-source health metrics across all countries. Never raises;
    on any unhandled error it logs a warning and leaves the previous file in place.
    """
    try:
        _generate_health_inner(output_dir, db_path)
    except Exception as exc:
        log.warning("generate_health failed (non-fatal): %s", exc)


def _generate_health_inner(output_dir: str, db_path: str) -> None:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Load inputs
    all_sources = _load_all_sources()
    status_by_country = _load_status_files(output_dir)
    db_stats = _db_stats_per_source(db_path) if os.path.exists(db_path) else {}
    prev_health = _load_previous_health(output_dir)

    # Per-country last_run_at for the top-level summary
    country_last_run: dict[str, str] = {
        c: s.get("last_run", "") for c, s in status_by_country.items()
    }

    # Index per-source status data from all country status files
    per_source_status: dict[str, dict] = {}
    for status in status_by_country.values():
        for entry in status.get("per_source", []):
            per_source_status[entry["name"]] = {**entry, "_country": status.get("country", "")}

    # Feed item counts per XML file
    feed_item_counts: dict[str, int] = {}
    feed_warnings: list[dict] = []
    xml_files = sorted(glob.glob(os.path.join(output_dir, "*.xml")))
    for xml_path in xml_files:
        fname = os.path.basename(xml_path)
        count = _count_xml_items(xml_path)
        feed_item_counts[fname] = count

        # Same-link detection (Step 3)
        links = _extract_links(xml_path)
        if links:
            from collections import Counter  # noqa: PLC0415
            link_counts = Counter(links)
            dupes = {lnk: n for lnk, n in link_counts.items() if n >= 5}
            if dupes:
                feed_warnings.append({
                    "feed": fname,
                    "type": "duplicate_link",
                    "links": dupes,
                })
            # Bare-path collision count (query-identified items)
            bare_counts = Counter(_bare_path(lnk) for lnk in links)
            query_identified = sum(n for n in bare_counts.values() if n > 1)
            if query_identified:
                feed_warnings.append({
                    "feed": fname,
                    "type": "query_identified_items",
                    "count": query_identified,
                })

    # Determine which feed files correspond to which (country, category) pairs
    # so we can flag no_sources feeds.
    enabled_feeds: set[str] = set()
    for s in all_sources:
        if not s.get("enabled", True):
            continue
        ck = s.get("_country_key", "uk")
        cat = s.get("category", "general")
        enabled_feeds.add(f"{ck}-{cat}.xml")

    # All possible feed files from FEED_META
    all_possible_feeds: set[str] = set()
    for ck, cats in COUNTRY_CATEGORIES.items():
        for cat in cats:
            all_possible_feeds.add(f"{ck}-{cat}.xml")

    # Build per-source records
    source_records: list[dict] = []
    # Deduplicate by source name (a name may appear in only one YAML)
    seen_names: set[str] = set()

    for source in all_sources:
        name = source.get("name", "")
        if name in seen_names:
            continue
        seen_names.add(name)

        country_key = source.get("_country_key", "uk")
        category = source.get("category", "general")
        feed_filename = f"{country_key}-{category}.xml"
        scraper_tier = source.get("scraper", "generic")
        enabled = source.get("enabled", True)
        is_intl_graduate = country_key == "internship_graduate"

        # Current run status for this source
        run_entry = per_source_status.get(name, {})
        last_run_at = status_by_country.get(country_key, {}).get("last_run", None)
        last_run_failed = run_entry.get("status") == "failed"
        last_run_new = run_entry.get("jobs_found", None) if run_entry else None
        last_run_found = last_run_new  # same field; spec uses both names
        last_error = run_entry.get("notes", None) if last_run_failed else None

        # last_success_at: from current run if succeeded, else carry forward
        prev = prev_health.get(name, {})
        if run_entry and run_entry.get("status") == "success":
            last_success_at = last_run_at
        else:
            last_success_at = prev.get("last_success_at")

        # consecutive_zero_runs: carry forward from previous health.json, reset on >0
        prev_czr = prev.get("consecutive_zero_runs", 0) or 0
        if run_entry:
            if run_entry.get("status") == "success" and (run_entry.get("jobs_found") or 0) == 0:
                consecutive_zero_runs = prev_czr + 1
            elif run_entry.get("status") == "success":
                consecutive_zero_runs = 0
            else:
                consecutive_zero_runs = prev_czr  # failure doesn't reset zero streak
        else:
            consecutive_zero_runs = prev_czr

        # DB-derived fields (null for internship_graduate)
        db = db_stats.get(name, {}) if not is_intl_graduate else {}
        active_rows = db.get("active_rows", None) if not is_intl_graduate else None
        new_7d = db.get("new_7d", None) if not is_intl_graduate else None
        new_28d = db.get("new_28d", None) if not is_intl_graduate else None
        new_prev_28d = db.get("new_prev_28d", None) if not is_intl_graduate else None
        median_lifetime_days = db.get("median_lifetime_days", None) if not is_intl_graduate else None
        stub_share = db.get("stub_share", None) if not is_intl_graduate else None

        is_cyclical = source.get("cyclical", False)
        status_enum = _compute_status_enum(
            enabled=enabled,
            last_success_at=last_success_at,
            new_7d=new_7d if new_7d is not None else 0,
            new_28d=new_28d if new_28d is not None else 0,
            new_prev_28d=new_prev_28d if new_prev_28d is not None else 0,
            consecutive_zero_runs=consecutive_zero_runs,
            is_cyclical=is_cyclical,
            last_run_failed=last_run_failed,
            is_intl_graduate=is_intl_graduate,
        )

        source_records.append({
            "name": name,
            "country": country_key,
            "category": category,
            "feed": feed_filename,
            "scraper_tier": scraper_tier,
            "enabled": enabled,
            "last_run_at": last_run_at,
            "last_success_at": last_success_at,
            "last_run_new": last_run_new,
            "last_run_found": last_run_found,
            "last_run_failed": last_run_failed,
            "last_error": last_error,
            "active_rows": active_rows,
            "new_7d": new_7d,
            "new_28d": new_28d,
            "new_prev_28d": new_prev_28d,
            "median_lifetime_days": median_lifetime_days,
            "stub_share": stub_share,
            "consecutive_zero_runs": consecutive_zero_runs,
            "status": status_enum,
        })

    # closing_soon: sources (by source_name from DB) where >= 80% of active rows
    # close within 3 days of date_first_seen (e.g. Civil Service Jobs).
    # Checked across all source_names in DB stats, not only those defined in YAML,
    # so that the warning fires even for sources not yet in any config file.
    for sn, sdata in db_stats.items():
        cs_share = sdata.get("closing_soon_share", 0.0) or 0.0
        if cs_share >= 0.8:
            feed_warnings.append({
                "source": sn,
                "type": "closing_soon",
                "closing_soon_share": cs_share,
            })

    # no_sources: feeds that exist on disk but have no enabled sources
    for fname in all_possible_feeds:
        if fname not in enabled_feeds:
            feed_warnings.append({
                "feed": fname,
                "type": "no_sources",
            })

    health = {
        "generated_at": generated_at,
        "country_last_run": country_last_run,
        "feed_item_counts": feed_item_counts,
        "warnings": feed_warnings,
        "sources": source_records,
    }

    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "health.json"), "w") as f:
        json.dump(health, f, indent=2)
    log.info("generate_health: wrote feeds/health.json (%d sources)", len(source_records))
