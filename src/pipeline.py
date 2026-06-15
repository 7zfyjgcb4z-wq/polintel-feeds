from __future__ import annotations

import asyncio
import importlib
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from src.db.store import JobStore
from src.enrichment.readability_enricher import enrich_jobs
from src.feed.generator import generate_alerts, generate_feeds, generate_status
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
    "us": CONFIG_DIR / "sources-us.yaml",
    "dach": CONFIG_DIR / "sources-dach.yaml",
    "southern": CONFIG_DIR / "sources-southern.yaml",
    "benelux": CONFIG_DIR / "sources-benelux.yaml",
    "nordics": CONFIG_DIR / "sources-nordics.yaml",
    "cee": CONFIG_DIR / "sources-cee.yaml",
    "pan-eu": CONFIG_DIR / "sources-pan-eu.yaml",
}

# Regions that use country_code (ISO alpha-2) per source rather than a country
# field; the pipeline injects country = region at load time so the DB and feed
# generator route jobs correctly.
EU_NATIONAL_REGIONS = {"dach", "southern", "benelux", "nordics", "cee", "pan-eu"}


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
    # "all" runs each country's pipeline sequentially and returns aggregated totals
    if country == "all":
        combined: dict = {"total": 0, "new": 0, "active": 0, "failed": []}
        for c in ["uk", "brussels", "us", "dach", "southern", "benelux", "nordics", "cee", "pan-eu"]:
            result = await run_pipeline(
                country=c,
                sources=sources,
                skip_ai=skip_ai,
                dry_run=dry_run,
                db_path=db_path,
                output_dir=output_dir,
                base_url=base_url,
            )
            combined["total"] += result["total"]
            combined["new"] += result["new"]
            combined["active"] += result["active"]
            combined["failed"].extend(result["failed"])
        return combined

    pipeline_start = time.monotonic()

    config_path = COUNTRY_CONFIG.get(country, CONFIG_PATH)
    config = load_config(config_path)
    db = JobStore(db_path)

    all_sources = config["sources"]

    # For EU national regions, sources use country_code (ISO alpha-2) for geo-tagging
    # but no pipeline-level country field. Inject country = region so ATS extractors
    # store the correct region tag in the DB and feeds are routed correctly.
    if country in EU_NATIONAL_REGIONS:
        for s in all_sources:
            s.setdefault("country", country)
    disabled = [s for s in all_sources if not s.get("enabled", True)]

    active_sources = [s for s in all_sources if s.get("enabled", True)]
    if country and country != "all":
        active_sources = [s for s in active_sources if s.get("country", "uk") == country]
    if sources:
        active_sources = [s for s in active_sources if s["name"] in sources]

    all_jobs: list[Job] = []
    sources_checked = 0
    sources_succeeded = 0
    failed_sources: list[str] = []

    no_enrich_sources: set[str] = {
        s["name"] for s in active_sources
        if s.get("enrich_description") is False
    }

    # Per-source monitoring state
    per_source_results: list[dict] = []
    per_source_by_name: dict[str, dict] = {}

    def _record(name: str, scraper_type: str, status: str,
                jobs_found: int, elapsed: float, notes: str = "") -> dict:
        entry: dict = {
            "name": name,
            "scraper_type": scraper_type,
            "status": status,
            "jobs_found": jobs_found,
            "jobs_after_relevance_filter": jobs_found,  # updated after filter pass
            "descriptions_enriched": 0,                 # updated after enrichment
            "duration_seconds": round(elapsed, 1),
        }
        if notes:
            entry["notes"] = notes
        per_source_results.append(entry)
        per_source_by_name[name] = entry
        return entry

    # ── Tier 1: Dedicated scrapers ────────────────────────────────────────────
    dedicated = [s for s in active_sources if s.get("scraper") == "dedicated"]
    for source in dedicated:
        sources_checked += 1
        t = time.monotonic()
        try:
            scraper = load_dedicated_scraper(source)
            jobs = await scraper.scrape()
            elapsed = time.monotonic() - t
            all_jobs.extend(jobs)
            sources_succeeded += 1
            entry = _record(source["name"], "dedicated", "success", len(jobs), elapsed)
            # Propagate optional upstream metadata (e.g. staleness info from
            # scrapers that consume third-party maintained data sources).
            if upstream := getattr(scraper, "upstream_meta", None):
                entry.update(upstream)
        except Exception as e:
            elapsed = time.monotonic() - t
            log.error(f"FAIL: {source['name']}: {e}")
            failed_sources.append(source["name"])
            _record(source["name"], "dedicated", "failed", 0, elapsed, str(e)[:200])

    # ── ATS auto scrapers ─────────────────────────────────────────────────────
    ats_sources = [s for s in active_sources if s.get("scraper") == "ats_auto"]
    if ats_sources:
        from src.scrapers.ats_detector import detect_ats  # noqa: PLC0415
        from src.scrapers.ats_extractors import get_extractor, PLATFORM_EXTRACTORS  # noqa: PLC0415

        for source in ats_sources:
            sources_checked += 1
            t = time.monotonic()
            try:
                if source.get("requires_js", False):
                    elapsed = time.monotonic() - t
                    log.warning(f"{source['name']}: requires_js=true — skipping (Playwright not enabled)")
                    failed_sources.append(source["name"])
                    _record(source["name"], "ats_auto", "failed", 0, elapsed, "requires_js=true (Playwright not enabled)")
                    continue

                # New API-based path: 'platform' field triggers direct API call (no HTML fetch).
                # Legacy 'ats_type' field still routes through the HTML-based detection path.
                platform = source.get("platform")
                if platform and platform in PLATFORM_EXTRACTORS:
                    api_extractor = PLATFORM_EXTRACTORS[platform]
                    jobs = await api_extractor.extract(source)
                    elapsed = time.monotonic() - t
                    all_jobs.extend(jobs)
                    sources_succeeded += 1
                    log.info(f"OK: {source['name']} (API:{platform}) — {len(jobs)} jobs")
                    _record(source["name"], "ats_auto", "success", len(jobs), elapsed)
                    continue

                # HTML-based detection/extraction path (legacy ats_type or auto-detection).
                html = await _fetch_html(source["url"])
                ats_type = source.get("ats_type") or detect_ats(html, source["url"])

                # AI fallback is gated behind ALLOW_AI_FALLBACK=1 (default OFF).
                # When off, ats_auto sources with no zero-API extractor are skipped
                # cleanly rather than incurring per-source Claude API calls.
                # The generic_scrape code stays in the repo and is importable for
                # deliberate one-off use; it just does not fire in normal runs.
                _allow_ai = os.environ.get("ALLOW_AI_FALLBACK", "").lower() in ("1", "true", "yes")

                if not ats_type:
                    if not _allow_ai:
                        elapsed = time.monotonic() - t
                        log.info(
                            f"{source['name']}: no zero-API extractor available — skipped"
                            f" (set ALLOW_AI_FALLBACK=1 to enable AI fallback)"
                        )
                        _record(source["name"], "ats_auto", "skipped", 0, elapsed,
                                "no zero-API extractor (AI fallback disabled)")
                        continue
                    from src.scrapers.generic import generic_scrape  # noqa: PLC0415
                    log.info(f"{source['name']}: no ATS detected — routing to AI fallback")
                    jobs = await generic_scrape(source, db, dry_run=dry_run)
                    elapsed = time.monotonic() - t
                    all_jobs.extend(jobs)
                    sources_succeeded += 1
                    log.info(f"OK: {source['name']} (AI fallback) — {len(jobs)} jobs")
                    _record(source["name"], "ats_auto", "success", len(jobs), elapsed,
                            "AI fallback (no ATS detected)")
                    continue

                extractor = get_extractor(ats_type)
                if extractor.__module__.endswith("_default_stub"):
                    if not _allow_ai:
                        elapsed = time.monotonic() - t
                        log.info(
                            f"{source['name']}: ATS={ats_type!r} has no extractor — skipped"
                            f" (set ALLOW_AI_FALLBACK=1 to enable AI fallback)"
                        )
                        _record(source["name"], "ats_auto", "skipped", 0, elapsed,
                                f"ATS={ats_type} detected but no extractor (AI fallback disabled)")
                        continue
                    from src.scrapers.generic import generic_scrape  # noqa: PLC0415
                    log.info(
                        f"{source['name']}: ATS={ats_type!r} has no extractor — routing to AI fallback"
                    )
                    jobs = await generic_scrape(source, db, dry_run=dry_run)
                    elapsed = time.monotonic() - t
                    all_jobs.extend(jobs)
                    sources_succeeded += 1
                    log.info(f"OK: {source['name']} (AI fallback, ATS={ats_type}) — {len(jobs)} jobs")
                    _record(source["name"], "ats_auto", "success", len(jobs), elapsed,
                            f"AI fallback (ATS={ats_type}, no extractor)")
                    continue

                jobs = extractor(html, source["url"], source)
                elapsed = time.monotonic() - t
                all_jobs.extend(jobs)
                sources_succeeded += 1
                log.info(f"OK: {source['name']} (ATS: {ats_type}) — {len(jobs)} jobs")
                _record(source["name"], "ats_auto", "success", len(jobs), elapsed)
            except Exception as e:
                elapsed = time.monotonic() - t
                log.error(f"FAIL: {source['name']}: {e}")
                failed_sources.append(source["name"])
                _record(source["name"], "ats_auto", "failed", 0, elapsed, str(e)[:200])

    # ── Selector scrapers ─────────────────────────────────────────────────────
    selector_sources = [s for s in active_sources if s.get("scraper") == "selector"]
    if selector_sources:
        from src.scrapers.selector_scraper import SelectorScraper  # noqa: PLC0415
        sel_scraper = SelectorScraper()

        for source in selector_sources:
            sources_checked += 1
            t = time.monotonic()
            try:
                selectors = source.get("selectors", {})
                jobs = await sel_scraper.scrape(source["url"], selectors, source)
                elapsed = time.monotonic() - t
                all_jobs.extend(jobs)
                sources_succeeded += 1
                log.info(f"OK: {source['name']} (selector) — {len(jobs)} jobs")
                _record(source["name"], "selector", "success", len(jobs), elapsed)
            except Exception as e:
                elapsed = time.monotonic() - t
                log.error(f"FAIL: {source['name']}: {e}")
                failed_sources.append(source["name"])
                _record(source["name"], "selector", "failed", 0, elapsed, str(e)[:200])

    # ── RSS feed scrapers ─────────────────────────────────────────────────────
    rss_sources = [s for s in active_sources if s.get("scraper") == "rss_feed"]
    if rss_sources:
        from src.scrapers.rss_feed_scraper import RSSFeedScraper  # noqa: PLC0415
        rss_scraper = RSSFeedScraper()

        for source in rss_sources:
            sources_checked += 1
            t = time.monotonic()
            try:
                field_map = source.get("field_map", {})
                jobs = await rss_scraper.scrape(source["url"], field_map, source)
                elapsed = time.monotonic() - t
                all_jobs.extend(jobs)
                sources_succeeded += 1
                log.info(f"OK: {source['name']} (rss_feed) — {len(jobs)} jobs")
                _record(source["name"], "rss_feed", "success", len(jobs), elapsed)
            except Exception as e:
                elapsed = time.monotonic() - t
                log.error(f"FAIL: {source['name']}: {e}")
                failed_sources.append(source["name"])
                _record(source["name"], "rss_feed", "failed", 0, elapsed, str(e)[:200])

    # ── Generic (deprecated) ──────────────────────────────────────────────────
    generic_sources = [s for s in active_sources if s.get("scraper") == "generic"]
    for source in generic_sources:
        log.warning(
            f"DEPRECATED: {source['name']} uses scraper=generic (Claude API) — "
            "skipping. Convert to selector, rss_feed, or ats_auto."
        )

    # ── Relevance filter ──────────────────────────────────────────────────────
    pre_filter_total = len(all_jobs)
    pre_by_source: dict[str, int] = {}
    for j in all_jobs:
        pre_by_source[j.source_name] = pre_by_source.get(j.source_name, 0) + 1

    all_jobs = filter_relevant_jobs(all_jobs)
    relevance_filtered = pre_filter_total - len(all_jobs)

    post_by_source: dict[str, int] = {}
    for j in all_jobs:
        post_by_source[j.source_name] = post_by_source.get(j.source_name, 0) + 1

    try:
        for entry in per_source_results:
            entry["jobs_after_relevance_filter"] = post_by_source.get(entry["name"], 0)
    except Exception as exc:
        log.warning(f"Per-source filter tracking failed (non-fatal): {exc}")

    # ── Description enrichment ────────────────────────────────────────────────
    jobs_to_enrich = [j for j in all_jobs if j.source_name not in no_enrich_sources]
    jobs_no_enrich = [j for j in all_jobs if j.source_name in no_enrich_sources]

    # Snapshot pre-enrichment state for per-source tracking
    pre_enrich_len: dict[str, int] = {j.guid: len(j.description or "") for j in jobs_to_enrich}
    needs_enrich: set[str] = {
        j.guid for j in jobs_to_enrich
        if not j.description or len(j.description.strip()) < 200
    }
    source_needed_enrich: dict[str, int] = {}
    for j in jobs_to_enrich:
        if j.guid in needs_enrich:
            source_needed_enrich[j.source_name] = source_needed_enrich.get(j.source_name, 0) + 1

    if jobs_to_enrich:
        jobs_to_enrich = await enrich_jobs(jobs_to_enrich)

    enriched_by_source: dict[str, int] = {}
    for j in jobs_to_enrich:
        if j.guid in needs_enrich and len(j.description or "") > pre_enrich_len.get(j.guid, 0) + 10:
            enriched_by_source[j.source_name] = enriched_by_source.get(j.source_name, 0) + 1
    total_enriched = sum(enriched_by_source.values())

    try:
        for entry in per_source_results:
            name = entry["name"]
            if name in no_enrich_sources:
                entry["descriptions_enriched"] = 0
                if entry["jobs_found"] > 0 and "notes" not in entry:
                    entry["notes"] = "Description enrichment disabled for this source"
            else:
                count = enriched_by_source.get(name, 0)
                entry["descriptions_enriched"] = count
                if entry["jobs_found"] > 0 and count == 0 and "notes" not in entry:
                    if source_needed_enrich.get(name, 0) == 0:
                        entry["notes"] = "Descriptions already substantive — enrichment skipped"
                    else:
                        entry["notes"] = "Enrichment skipped or failed — captcha or fetch error likely"
    except Exception as exc:
        log.warning(f"Per-source enrichment tracking failed (non-fatal): {exc}")

    all_jobs = jobs_to_enrich + jobs_no_enrich

    # ── Location extraction ───────────────────────────────────────────────────
    # Fills job.location where it is not already set by a dedicated scraper.
    # Dedicated scrapers (e.g. eutraining, house_employment_bulletin) populate
    # location from structured upstream data; those values are preserved.
    try:
        from src.utils.location_extractor import extract_location  # noqa: PLC0415

        loc_stats: dict[str, dict] = {}
        unmatched_prefixes: list[str] = []

        for job in all_jobs:
            src = job.source_name
            if src not in loc_stats:
                loc_stats[src] = {"total": 0, "extracted": 0}
            loc_stats[src]["total"] += 1

            if job.location:
                # Already set by dedicated scraper — preserve it.
                loc_stats[src]["extracted"] += 1
                continue

            try:
                result = extract_location(
                    description=job.description,
                    url=job.url,
                    title=job.title,
                    creator=None,
                )
                job.location = result
                if result:
                    loc_stats[src]["extracted"] += 1
                else:
                    prefix = (job.description or "")[:80].strip()
                    if prefix:
                        unmatched_prefixes.append(prefix)
            except Exception as exc:
                log.warning(f"location extraction failed [{src}] {job.url}: {exc}")

        # Summary log by source
        summary_lines = ["location-extraction summary:"]
        for src_name, counts in sorted(loc_stats.items()):
            total = counts["total"]
            extracted = counts["extracted"]
            null_count = total - extracted
            pct_ex = round(100 * extracted / total) if total else 0
            pct_null = 100 - pct_ex
            summary_lines.append(
                f"  {src_name}: total={total} extracted={extracted}"
                f" ({pct_ex}%) null={null_count} ({pct_null}%)"
            )
        log.info("\n".join(summary_lines))

        # Top 20 unmatched prefixes to guide future layer improvements
        if unmatched_prefixes:
            top = unmatched_prefixes[:20]
            prefix_lines = ["top unmatched description prefixes (first 80 chars):"]
            for p in top:
                prefix_lines.append(f"  {p!r}")
            log.info("\n".join(prefix_lines))

    except Exception as exc:
        log.warning(f"Location extraction pass failed (non-fatal): {exc}")

    # ── Store ─────────────────────────────────────────────────────────────────
    new_count = db.upsert_jobs(all_jobs)
    db.expire_by_closing_date()
    db.mark_stale(days=30)
    db.purge_old(days=90)

    # ── Generate feeds ────────────────────────────────────────────────────────
    active_jobs = db.get_active_jobs(country=country)
    feed_counts = generate_feeds(active_jobs, output_dir=output_dir, base_url=base_url, country=country)

    # ── Per-source log summaries ──────────────────────────────────────────────
    try:
        country_tag = country.upper()
        for entry in per_source_results:
            name = entry["name"]
            stype = entry["scraper_type"]
            found = entry["jobs_found"]
            after_filter = entry["jobs_after_relevance_filter"]
            enriched = entry["descriptions_enriched"]
            dur = entry["duration_seconds"]
            status = entry["status"]
            notes = entry.get("notes", "")

            if status == "failed":
                note_str = f" ({notes})" if notes else ""
                log.warning(f"[{country_tag}] {name}: {stype} — FAILED{note_str} [{dur}s]")
                continue

            parts = [f"[{country_tag}] {name}: {stype} — {found} found"]
            if after_filter != found:
                parts.append(f"{after_filter} after filter")
            if found > 0:
                if name in no_enrich_sources:
                    parts.append("0 enriched (disabled)")
                elif source_needed_enrich.get(name, 0) == 0:
                    parts.append(f"{enriched} enriched (already substantive)")
                else:
                    parts.append(f"{enriched} enriched")
            log.info(" — ".join(parts) + f" [{dur}s]")

        log.info(f"Skipped {len(disabled)} disabled sources.")

        total_elapsed = time.monotonic() - pipeline_start
        if total_elapsed > 25 * 60:
            log.warning(f"Pipeline exceeded 25-minute threshold ({total_elapsed / 60:.1f} min total)")
        for entry in per_source_results:
            if entry["duration_seconds"] > 60:
                log.warning(
                    f"{entry['name']} took {entry['duration_seconds']}s — exceeds 60s threshold"
                )
    except Exception as exc:
        log.warning(f"Per-source log summaries failed (non-fatal): {exc}")

    # ── Health monitoring: alerts then status (order matters — alerts reads old status.json) ──
    total_duration = round(time.monotonic() - pipeline_start, 1)
    prev_status_path = os.path.join(output_dir, "status.json")
    prev_alerts_path = os.path.join(output_dir, "alerts.json")

    try:
        generate_alerts(
            output_dir=output_dir,
            current_per_source=per_source_results,
            previous_status_path=prev_status_path,
            previous_alerts_path=prev_alerts_path,
        )
    except Exception as exc:
        log.error(f"Alert generation failed (non-fatal): {exc}")

    try:
        generate_status(
            output_dir=output_dir,
            country=country,
            sources_checked=sources_checked,
            sources_succeeded=sources_succeeded,
            sources_failed=len(failed_sources),
            failed_sources=failed_sources,
            new_jobs_found=new_count,
            total_active_jobs=len(active_jobs),
            feeds_generated=len(feed_counts),
            per_source=per_source_results,
            sources_disabled=len(disabled),
            relevance_filtered=relevance_filtered,
            descriptions_enriched=total_enriched,
            run_duration_seconds=total_duration,
        )
    except Exception as exc:
        log.error(f"Status generation failed (non-fatal): {exc}")

    db.close()
    log.info(f"Done: {len(all_jobs)} total scraped, {new_count} new")
    return {
        "total": len(all_jobs),
        "new": new_count,
        "active": len(active_jobs),
        "failed": failed_sources,
    }
