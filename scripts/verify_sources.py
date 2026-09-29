"""Verification harness for UK source expansion candidates.

Reads candidates/uk_expansion.yaml. For each candidate:
  - Checks robots.txt for the relevant scrape path
  - Fetches once via the real extractor (detail_ceiling=1 for Workday/OracleHCM)
  - Applies proposed title/location filters and reports both raw and filtered counts
  - Records 5 sample titles (raw and filtered-out)
  - Writes verification/uk_expansion_results.md and .json

Politeness: one listing request per source plus at most one detail page.
Per-host concurrency: 1 (sequential per host, asyncio gather across distinct hosts).

Run: python scripts/verify_sources.py [--candidate NAME]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import yaml

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.scrapers.base import USER_AGENT
from src.scrapers.ats_extractors.api_extractors import (
    BambooHRAPIExtractor,
    GreenhouseAPIExtractor,
    OracleHCMAPIExtractor,
    PersonioAPIExtractor,
    TeamTailorAPIExtractor,
    WorkdayAPIExtractor,
)
from src.scrapers.selector_scraper import SelectorScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

CANDIDATES_PATH = PROJECT_ROOT / "candidates" / "uk_expansion.yaml"
OUTPUT_DIR = PROJECT_ROOT / "verification"

# Proposed title filters applied to report filtered counts (not applied to actual storage)
_INCLUDE_PAT = re.compile(
    r"policy|regulat|supervis|econom|public affairs|government affairs|"
    r"strategy|research|analyst|parliament|legislat|stakeholder|"
    r"communications|advocacy|campaign|graduate|intern",
    re.IGNORECASE,
)
_EXCLUDE_PAT = re.compile(
    r"facilities|cleaner|catering|payroll|accounts payable|IT support|"
    r"service desk|security officer|receptionist|driver",
    re.IGNORECASE,
)

_CHALLENGE_PATTERNS = re.compile(
    r"captcha|cf-challenge|just a moment|challenge-running|"
    r"bot.?detection|access.?denied|cloudflare.ray|enable.?javascript",
    re.IGNORECASE,
)


def _check_robots(host: str, path: str) -> str:
    """Return 'allow', 'disallow', or 'error:{msg}'."""
    robots_url = f"https://{host}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        allowed = rp.can_fetch(USER_AGENT, f"https://{host}{path}")
        return "allow" if allowed else "disallow"
    except Exception as exc:
        return f"error:{exc}"


def _apply_filter(jobs, candidate: dict) -> list:
    """Return jobs that pass the candidate's title_include/exclude and location_filter."""
    include_pat_src = candidate.get("title_include_regex")
    exclude_pat_src = candidate.get("title_exclude_regex")
    location_filter = candidate.get("location_filter")

    include_re = re.compile(include_pat_src, re.IGNORECASE) if include_pat_src else None
    exclude_re = re.compile(exclude_pat_src, re.IGNORECASE) if exclude_pat_src else None
    location_re = re.compile(location_filter, re.IGNORECASE) if location_filter else None

    out = []
    for j in jobs:
        title = j.title or ""
        if include_re and not include_re.search(title):
            continue
        if exclude_re and exclude_re.search(title):
            continue
        if location_re:
            loc = j.location or ""
            if loc and not location_re.search(loc):
                continue
        out.append(j)
    return out


def _detect_challenge(resp: httpx.Response) -> bool:
    if resp.status_code in (403, 429, 503):
        return True
    return bool(_CHALLENGE_PATTERNS.search(resp.text[:4000]))


async def _verify_workday(candidate: dict) -> dict:
    ident = candidate.get("identifier", {})
    tenant = ident.get("tenant", "")
    dc = ident.get("dc", "")
    site = ident.get("site", "")
    host = f"{tenant}.{dc}.myworkdayjobs.com"
    robots = _check_robots(host, f"/wday/cxs/{tenant}/{site}/jobs")

    extractor = WorkdayAPIExtractor()
    source = dict(candidate)
    source.setdefault("org_static", candidate.get("org_static") or candidate.get("name", ""))
    source["detail_fetch_budget"] = 1
    t = time.monotonic()
    try:
        jobs = await extractor.extract(source, detail_ceiling=1)
        http_status = "200"
        challenge = False
    except httpx.HTTPStatusError as exc:
        jobs = []
        http_status = str(exc.response.status_code)
        challenge = _detect_challenge(exc.response)
    except Exception as exc:
        jobs = []
        http_status = f"error:{exc}"
        challenge = False
    elapsed = round(time.monotonic() - t, 1)

    filtered = _apply_filter(jobs, candidate)
    return _build_result(candidate, robots, http_status, challenge, jobs, filtered, elapsed)


async def _verify_oracle_hcm(candidate: dict) -> dict:
    ident = candidate.get("identifier", {})
    api_host = ident.get("api_host", "")
    site = ident.get("site", "")
    robots = _check_robots(api_host, "/hcmRestApi/resources/latest/recruitingCEJobRequisitions")

    extractor = OracleHCMAPIExtractor()
    source = dict(candidate)
    source.setdefault("org_static", candidate.get("org_static") or candidate.get("name", ""))
    source["detail_fetch_budget"] = 1
    t = time.monotonic()
    try:
        jobs = await extractor.extract(source, detail_ceiling=1)
        http_status = "200"
        challenge = False
    except httpx.HTTPStatusError as exc:
        jobs = []
        http_status = str(exc.response.status_code)
        challenge = _detect_challenge(exc.response)
    except Exception as exc:
        jobs = []
        http_status = f"error:{exc}"
        challenge = False
    elapsed = round(time.monotonic() - t, 1)

    filtered = _apply_filter(jobs, candidate)
    return _build_result(candidate, robots, http_status, challenge, jobs, filtered, elapsed)


async def _verify_greenhouse(candidate: dict) -> dict:
    ident = candidate.get("identifier", {})
    token = ident.get("token", "")
    robots = _check_robots("boards-api.greenhouse.io", f"/v1/boards/{token}/jobs")

    extractor = GreenhouseAPIExtractor()
    source = dict(candidate)
    source.setdefault("org_static", candidate.get("org_static") or candidate.get("name", ""))
    t = time.monotonic()
    try:
        jobs = await extractor.extract(source)
        http_status = "200"
        challenge = False
    except httpx.HTTPStatusError as exc:
        jobs = []
        http_status = str(exc.response.status_code)
        challenge = _detect_challenge(exc.response)
    except Exception as exc:
        jobs = []
        http_status = f"error:{exc}"
        challenge = False
    elapsed = round(time.monotonic() - t, 1)

    filtered = _apply_filter(jobs, candidate)
    return _build_result(candidate, robots, http_status, challenge, jobs, filtered, elapsed)


async def _verify_teamtailor(candidate: dict) -> dict:
    ident = candidate.get("identifier", {})
    base_url = ident.get("base_url", "")
    robots = _check_robots(base_url, "/jobs.json")

    extractor = TeamTailorAPIExtractor()
    source = dict(candidate)
    source.setdefault("org_static", candidate.get("org_static") or candidate.get("name", ""))
    t = time.monotonic()
    try:
        jobs = await extractor.extract(source)
        http_status = "200"
        challenge = False
    except httpx.HTTPStatusError as exc:
        jobs = []
        http_status = str(exc.response.status_code)
        challenge = _detect_challenge(exc.response)
    except Exception as exc:
        jobs = []
        http_status = f"error:{exc}"
        challenge = False
    elapsed = round(time.monotonic() - t, 1)

    filtered = _apply_filter(jobs, candidate)
    return _build_result(candidate, robots, http_status, challenge, jobs, filtered, elapsed)


async def _verify_personio(candidate: dict) -> dict:
    ident = candidate.get("identifier", {})
    subdomain = ident.get("subdomain", "")
    host = f"{subdomain}.jobs.personio.de"
    robots = _check_robots(host, "/xml")

    extractor = PersonioAPIExtractor()
    source = dict(candidate)
    source.setdefault("org_static", candidate.get("org_static") or candidate.get("name", ""))
    t = time.monotonic()
    try:
        jobs = await extractor.extract(source)
        http_status = "200"
        challenge = False
    except httpx.HTTPStatusError as exc:
        jobs = []
        http_status = str(exc.response.status_code)
        challenge = _detect_challenge(exc.response)
    except Exception as exc:
        jobs = []
        http_status = f"error:{exc}"
        challenge = False
    elapsed = round(time.monotonic() - t, 1)

    filtered = _apply_filter(jobs, candidate)
    return _build_result(candidate, robots, http_status, challenge, jobs, filtered, elapsed)


async def _verify_bamboohr(candidate: dict) -> dict:
    ident = candidate.get("identifier", {})
    company = ident.get("company", "")
    host = f"{company}.bamboohr.com"
    robots = _check_robots(host, "/careers/list")

    extractor = BambooHRAPIExtractor()
    source = dict(candidate)
    source.setdefault("org_static", candidate.get("org_static") or candidate.get("name", ""))
    source["detail_fetch_budget"] = 1
    t = time.monotonic()
    try:
        jobs = await extractor.extract(source)
        http_status = "200"
        challenge = False
    except httpx.HTTPStatusError as exc:
        jobs = []
        http_status = str(exc.response.status_code)
        challenge = _detect_challenge(exc.response)
    except Exception as exc:
        jobs = []
        http_status = f"error:{exc}"
        challenge = False
    elapsed = round(time.monotonic() - t, 1)

    filtered = _apply_filter(jobs, candidate)
    return _build_result(candidate, robots, http_status, challenge, jobs, filtered, elapsed)


async def _verify_selector(candidate: dict) -> dict:
    url = candidate.get("url", "")
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path or "/"
    robots = _check_robots(host, path)

    selectors = candidate.get("selectors", {})
    scraper = SelectorScraper()
    t = time.monotonic()
    http_status = "200"
    challenge = False
    jobs = []
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            resp = await client.get(url)
            http_status = str(resp.status_code)
            challenge = _detect_challenge(resp)
            resp.raise_for_status()
            if selectors.get("job_card"):
                jobs = scraper._parse(resp.text, url, selectors, candidate)
    except httpx.HTTPStatusError as exc:
        http_status = str(exc.response.status_code)
        challenge = _detect_challenge(exc.response)
    except Exception as exc:
        http_status = f"error:{exc}"
    elapsed = round(time.monotonic() - t, 1)

    filtered = _apply_filter(jobs, candidate)
    return _build_result(candidate, robots, http_status, challenge, jobs, filtered, elapsed)


def _build_result(
    candidate: dict,
    robots: str,
    http_status: str,
    challenge: bool,
    raw_jobs,
    filtered_jobs,
    elapsed: float,
) -> dict:
    raw_titles = [(j.title or "—", j.location or "—") for j in raw_jobs[:5]]
    filtered_out = [j for j in raw_jobs if j not in filtered_jobs]
    filtered_out_titles = [(j.title or "—", j.location or "—") for j in filtered_out[:5]]
    return {
        "name": candidate.get("name", ""),
        "platform": candidate.get("platform") or candidate.get("scraper", ""),
        "tier": candidate.get("tier", ""),
        "verify_only": candidate.get("verify_only", False),
        "robots": robots,
        "http_status": http_status,
        "challenge_detected": challenge,
        "raw_count": len(raw_jobs),
        "filtered_count": len(filtered_jobs),
        "sample_titles_raw": raw_titles,
        "sample_titles_filtered_out": filtered_out_titles,
        "elapsed_s": elapsed,
        "notes": candidate.get("notes", ""),
    }


_DISPATCH = {
    "workday": _verify_workday,
    "oracle_hcm": _verify_oracle_hcm,
    "greenhouse": _verify_greenhouse,
    "teamtailor": _verify_teamtailor,
    "personio": _verify_personio,
    "bamboohr": _verify_bamboohr,
    "selector": _verify_selector,
}

# Semaphore per host — key is the base hostname
_HOST_SEMAPHORES: dict[str, asyncio.Semaphore] = {}


def _host_for(candidate: dict) -> str:
    platform = candidate.get("platform") or candidate.get("scraper", "")
    ident = candidate.get("identifier", {})
    if platform == "workday":
        t, dc = ident.get("tenant", ""), ident.get("dc", "")
        return f"{t}.{dc}.myworkdayjobs.com"
    if platform == "oracle_hcm":
        return ident.get("api_host", "oracle")
    if platform == "greenhouse":
        return "boards-api.greenhouse.io"
    if platform == "teamtailor":
        return ident.get("base_url", "teamtailor.com")
    if platform == "personio":
        return f"{ident.get('subdomain', '')}.jobs.personio.de"
    if platform == "bamboohr":
        return f"{ident.get('company', '')}.bamboohr.com"
    url = candidate.get("url", "")
    return urlparse(url).netloc or "unknown"


async def _verify_with_semaphore(candidate: dict) -> dict:
    host = _host_for(candidate)
    if host not in _HOST_SEMAPHORES:
        _HOST_SEMAPHORES[host] = asyncio.Semaphore(1)
    platform = candidate.get("platform") or candidate.get("scraper", "")
    fn = _DISPATCH.get(platform)
    if fn is None:
        return {
            "name": candidate.get("name", ""),
            "platform": platform,
            "robots": "skip",
            "http_status": "unsupported_platform",
            "challenge_detected": False,
            "raw_count": 0,
            "filtered_count": 0,
            "sample_titles_raw": [],
            "sample_titles_filtered_out": [],
            "elapsed_s": 0,
            "notes": f"No verifier for platform {platform!r}",
        }
    async with _HOST_SEMAPHORES[host]:
        log.info("Verifying %s (%s) ...", candidate.get("name"), platform)
        return await fn(candidate)


def _write_markdown(results: list[dict], path: Path) -> None:
    lines = [
        "# UK Source Expansion — Verification Results",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Summary table",
        "",
        "| Source | Platform | Robots | HTTP | Challenge | Raw | Filtered | Elapsed |",
        "|--------|----------|--------|------|-----------|-----|----------|---------|",
    ]
    for r in results:
        verify_flag = " †" if r.get("verify_only") else ""
        name = r["name"] + verify_flag
        robots_icon = "✓" if r["robots"] == "allow" else ("✗" if r["robots"] == "disallow" else "?")
        challenge_icon = "⚠ YES" if r["challenge_detected"] else "no"
        lines.append(
            f"| {name} | {r['platform']} | {robots_icon} {r['robots']} | {r['http_status']} "
            f"| {challenge_icon} | {r['raw_count']} | {r['filtered_count']} | {r['elapsed_s']}s |"
        )
    lines += [
        "",
        "† verify_only — do not add to sources.yaml without explicit approval.",
        "",
        "## Sample titles",
        "",
    ]
    for r in results:
        lines.append(f"### {r['name']}")
        if r.get("notes"):
            lines.append(f"*{r['notes']}*")
        lines.append("")
        if r["raw_count"] == 0:
            lines.append("No jobs returned.")
        else:
            lines.append(f"**Raw ({r['raw_count']} total) — first 5:**")
            for title, loc in r.get("sample_titles_raw", []):
                lines.append(f"- {title} | {loc}")
            fo = r.get("sample_titles_filtered_out", [])
            if fo:
                lines.append(f"")
                lines.append(f"**Filtered out (sample — check for false negatives):**")
                for title, loc in fo:
                    lines.append(f"- {title} | {loc}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote %s", path)


def _write_json(results: list[dict], path: Path) -> None:
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Wrote %s", path)


async def main(candidate_name: str | None = None) -> None:
    with open(CANDIDATES_PATH) as f:
        config = yaml.safe_load(f)
    candidates = config.get("candidates", [])

    if candidate_name:
        candidates = [c for c in candidates if c.get("name") == candidate_name]
        if not candidates:
            log.error("Candidate %r not found in %s", candidate_name, CANDIDATES_PATH)
            sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    tasks = [_verify_with_semaphore(c) for c in candidates]
    results = await asyncio.gather(*tasks)

    md_path = OUTPUT_DIR / "uk_expansion_results.md"
    json_path = OUTPUT_DIR / "uk_expansion_results.json"
    _write_markdown(results, md_path)
    _write_json(results, json_path)

    blocked = [r for r in results if r["challenge_detected"] or r["robots"] == "disallow"]
    if blocked:
        log.warning("Blocked / disallowed sources: %s", [r["name"] for r in blocked])
    log.info(
        "Done: %d candidates verified, %d blocked/disallowed",
        len(results), len(blocked),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify UK source expansion candidates")
    parser.add_argument("--candidate", metavar="NAME", help="Verify a single candidate by name")
    args = parser.parse_args()
    asyncio.run(main(candidate_name=args.candidate))
