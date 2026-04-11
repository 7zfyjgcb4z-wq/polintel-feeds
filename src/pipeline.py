from __future__ import annotations

import asyncio
import importlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from src.db.store import JobStore
from src.enrichment.readability_enricher import enrich_jobs
from src.feed.generator import generate_feeds, generate_status
from src.filters.relevance import filter_relevant_jobs, is_relevant
from src.models.job import Job
from src.scrapers.base import USER_AGENT

log = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent / "config"
CONFIG_PATH = CONFIG_DIR / "sources.yaml"
EXCLUSIONS_PATH = CONFIG_DIR / "exclusions.yaml"

COUNTRY_CONFIG = {
    "uk": CONFIG_DIR / "sources.yaml",
    "brussels": CONFIG_DIR / "sources-brussels.yaml",
}


def load_config(path: str | Path = CONFIG_PATH) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_dedicated_scraper(source: dict):
    module_name = source.get("module")
    if not module_name:
        raise ValueError(f"No module specified for dedicated scraper: {source['name']}")
    mod = importlib.import_module(f"src.scrapers.dedicated.{module_name}")
    cls = getattr(mod, "Scraper")
    return cls(source)


def get_todays_batch(sources: list[dict], num_batches: int = 3) -> list[dict]:
    """Rotate sources so only ~1/3 run each day."""
    day_of_year = datetime.now(timezone.utc).timetuple().tm_yday
    batch_index = day_of_year % num_batches
    return [s for i, s in enumerate(sources) if i % num_batches == batch_index]


async def _fetch_html(url: str) -> str:
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=30.0,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


async def run_pipeline(
    country: str = "uk",
    sources: list[str] | None = None,
    skip_ai: bool = False,
    dry_run: bool = False,
    db_path: str = "data/jobs.db",
    output_dir: str = "feeds/",
    base_url: str = "",
) -> dict:
    config_path = COUNTRY_CONFIG.get(country, CONFIG_PATH)
    config = load_config(config_path)
    db = JobStore(db_path)

    # Separate enabled vs disabled sources for logging
    all_sources = config["sources"]
    disabled = [s for s in all_sources if not s.get("enabled", True)]
    for s in disabled:
        log.info(f"SKIPPED (disabled): {s['name']}")

    active_sources = [s for s in all_sources if s.get("enabled", True)]
    if country:
        active_sources = [s for s in active_sources if s.get("country", "uk") == country]
    if sources:
        active_sources = [s for s in active_sources if s["name"] in sources]

    all_jobs: list[Job] = []
    sources_checked = 0
    sources_succeeded = 0
    failed_sources: list[str] = []

    # Track which source names skip enrichment
    no_enrich_sources: set[str] = {
        s["name"] for s in active_sources
        if s.get("enrich_description") is False
    }

    # ── Tier 1: Dedicated scrapers ────────────────────────────────────────────
    dedicated = [s for s in active_sources if s.get("scraper") == "dedicated"]
    for source in dedicated:
        sources_checked += 1
        try:
            scraper = load_dedicated_scraper(source)
            jobs = await scraper.scrape()
            all_jobs.extend(jobs)
            sources_succeeded += 1
            log.info(f"OK: {source['name']} — {len(jobs)} jobs")
        except Exception as e:
            log.error(f"FAIL: {source['name']}: {e}")
            failed_sources.append(source["name"])

    # ── ATS auto scrapers ─────────────────────────────────────────────────────
    ats_sources = [s for s in active_sources if s.get("scraper") == "ats_auto"]
    if ats_sources:
        from src.scrapers.ats_detector import detect_ats  # noqa: PLC0415
        from src.scrapers.ats_extractors import get_extractor  # noqa: PLC0415

        for source in ats_sources:
            sources_checked += 1
            try:
                if source.get("requires_js", False):
                    log.warning(f"{source['name']}: requires_js=true — skipping (Playwright not enabled)")
                    failed_sources.append(source["name"])
                    continue

                html = await _fetch_html(source["url"])
                ats_type = source.get("ats_type") or detect_ats(html, source["url"])
                if not ats_type:
                    log.warning(f"{source['name']}: no ATS detected — skipping")
                    failed_sources.append(source["name"])
                    continue

                extractor = get_extractor(ats_type)
                if extractor.__module__.endswith("_default_stub"):
                    jobs = extractor(html, source["url"], source, ats_type=ats_type)
                else:
                    jobs = extractor(html, source["url"], source)

                all_jobs.extend(jobs)
                sources_succeeded += 1
                log.info(f"OK: {source['name']} (ATS: {ats_type}) — {len(jobs)} jobs")
            except Exception as e:
                log.error(f"FAIL: {source['name']}: {e}")
                failed_sources.append(source["name"])

    # ── Selector scrapers ─────────────────────────────────────────────────────
    selector_sources = [s for s in active_sources if s.get("scraper") == "selector"]
    if selector_sources:
        from src.scrapers.selector_scraper import SelectorScraper  # noqa: PLC0415
        sel_scraper = SelectorScraper()

        for source in selector_sources:
            sources_checked += 1
            try:
                selectors = source.get("selectors", {})
                jobs = await sel_scraper.scrape(source["url"], selectors, source)
                all_jobs.extend(jobs)
                sources_succeeded += 1
                log.info(f"OK: {source['name']} (selector) — {len(jobs)} jobs")
            except Exception as e:
                log.error(f"FAIL: {source['name']}: {e}")
                failed_sources.append(source["name"])

    # ── RSS feed scrapers ─────────────────────────────────────────────────────
    rss_sources = [s for s in active_sources if s.get("scraper") == "rss_feed"]
    if rss_sources:
        from src.scrapers.rss_feed_scraper import RSSFeedScraper  # noqa: PLC0415
        rss_scraper = RSSFeedScraper()

        for source in rss_sources:
            sources_checked += 1
            try:
                field_map = source.get("field_map", {})
                jobs = await rss_scraper.scrape(source["url"], field_map, source)
                all_jobs.extend(jobs)
                sources_succeeded += 1
                log.info(f"OK: {source['name']} (rss_feed) — {len(jobs)} jobs")
            except Exception as e:
                log.error(f"FAIL: {source['name']}: {e}")
                failed_sources.append(source["name"])

    # ── Generic (deprecated) ──────────────────────────────────────────────────
    generic_sources = [s for s in active_sources if s.get("scraper") == "generic"]
    for source in generic_sources:
        log.warning(
            f"DEPRECATED: {source['name']} uses scraper=generic (Claude API) — "
            "skipping. Convert to selector, rss_feed, or ats_auto."
        )

    # ── Relevance filter ──────────────────────────────────────────────────────
    all_jobs = filter_relevant_jobs(all_jobs)

    # ── Description enrichment ────────────────────────────────────────────────
    # Exclude jobs from sources that have enrich_description: false
    jobs_to_enrich = [j for j in all_jobs if j.source_name not in no_enrich_sources]
    jobs_no_enrich = [j for j in all_jobs if j.source_name in no_enrich_sources]

    if jobs_to_enrich:
        jobs_to_enrich = await enrich_jobs(jobs_to_enrich)

    all_jobs = jobs_to_enrich + jobs_no_enrich

    # ── Store ─────────────────────────────────────────────────────────────────
    new_count = db.upsert_jobs(all_jobs)
    db.mark_stale(days=30)
    db.purge_old(days=90)

    # ── Generate feeds ────────────────────────────────────────────────────────
    active_jobs = db.get_active_jobs(country=country)
    feed_counts = generate_feeds(active_jobs, output_dir=output_dir, base_url=base_url, country=country)

    generate_status(
        output_dir=output_dir,
        sources_checked=sources_checked,
        sources_succeeded=sources_succeeded,
        sources_failed=len(failed_sources),
        failed_sources=failed_sources,
        new_jobs_found=new_count,
        total_active_jobs=len(active_jobs),
        feeds_generated=len(feed_counts),
    )

    db.close()
    log.info(f"Done: {len(all_jobs)} total scraped, {new_count} new")
    return {
        "total": len(all_jobs),
        "new": new_count,
        "active": len(active_jobs),
        "failed": failed_sources,
    }
