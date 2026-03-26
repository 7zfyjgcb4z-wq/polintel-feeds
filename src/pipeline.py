from __future__ import annotations

import asyncio
import importlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.db.store import JobStore
from src.feed.generator import generate_feeds, generate_status
from src.models.job import Job

log = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config" / "sources.yaml"


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
    """Rotate generic sources so only ~1/3 run each day."""
    day_of_year = datetime.now(timezone.utc).timetuple().tm_yday
    batch_index = day_of_year % num_batches
    return [s for i, s in enumerate(sources) if i % num_batches == batch_index]


async def run_pipeline(
    country: str = "uk",
    sources: list[str] | None = None,
    skip_ai: bool = False,
    dry_run: bool = False,
    db_path: str = "data/jobs.db",
    output_dir: str = "feeds/",
    base_url: str = "",
) -> dict:
    config = load_config()
    db = JobStore(db_path)

    active_sources = [s for s in config["sources"] if s.get("enabled", True)]
    if country:
        active_sources = [s for s in active_sources if s.get("country", "uk") == country]
    if sources:
        active_sources = [s for s in active_sources if s["name"] in sources]

    all_jobs: list[Job] = []
    sources_checked = 0
    sources_succeeded = 0
    failed_sources: list[str] = []

    # Tier 1 dedicated scrapers
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

    # Tier 2 generic AI scrapers
    if not skip_ai:
        from src.scrapers.generic import generic_scrape  # noqa: PLC0415

        generic = [s for s in active_sources if s.get("scraper") == "generic"]
        # Skip rotation when specific sources are requested (e.g. during testing)
        today_batch = generic if sources else get_todays_batch(generic)
        for source in today_batch:
            sources_checked += 1
            try:
                jobs = await generic_scrape(source, db, dry_run=dry_run)
                all_jobs.extend(jobs)
                sources_succeeded += 1
                await asyncio.sleep(1)
            except Exception as e:
                log.error(f"FAIL: {source['name']}: {e}")
                failed_sources.append(source["name"])

    # Store
    new_count = db.upsert_jobs(all_jobs)
    db.mark_stale(days=30)
    db.purge_old(days=90)

    # Generate feeds
    active_jobs = db.get_active_jobs(country=country)
    feed_counts = generate_feeds(active_jobs, output_dir=output_dir, base_url=base_url)

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
