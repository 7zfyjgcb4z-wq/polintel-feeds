"""
Relevance filter: exclude jobs whose titles match known irrelevant keywords.

Single-word keywords use word-boundary regex (e.g. "cook" matches "Production Cook"
but not "Cookson"). Multi-word phrases use case-insensitive substring matching.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

from src.models.job import Job

log = logging.getLogger(__name__)

_WORD_BOUNDARY = re.compile(r"\s")  # used only to detect multi-word phrases


def _build_pattern(keyword: str) -> re.Pattern:
    if " " in keyword.strip():
        # Multi-word: simple substring match, case-insensitive
        return re.compile(re.escape(keyword), re.IGNORECASE)
    else:
        # Single word: word-boundary match
        return re.compile(r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE)


def filter_relevant_jobs(
    jobs: list[Job],
    exclusions_path: str = "src/config/exclusions.yaml",
) -> list[Job]:
    """
    Filter jobs by checking titles against an exclusion keyword list.
    Jobs whose titles match any exclusion keyword are discarded.
    Jobs that match nothing are kept.
    """
    path = Path(exclusions_path)
    if not path.exists():
        log.warning(f"Exclusions config not found at {exclusions_path}; skipping filter")
        return jobs

    with open(path) as f:
        config = yaml.safe_load(f)

    raw_keywords: list[str] = config.get("exclusions", [])
    if not raw_keywords:
        log.warning("No exclusion keywords found in config; skipping filter")
        return jobs

    patterns = [(kw, _build_pattern(kw)) for kw in raw_keywords]

    kept: list[Job] = []
    excluded_count = 0

    for job in jobs:
        matched_keyword: str | None = None
        for keyword, pattern in patterns:
            if pattern.search(job.title):
                matched_keyword = keyword
                break

        if matched_keyword:
            log.info(
                f'EXCLUDED: "{job.title}" at {job.organisation} — matched "{matched_keyword}"'
            )
            excluded_count += 1
        else:
            kept.append(job)

    total = len(jobs)
    kept_count = len(kept)
    log.info(
        f"Relevance filter: {kept_count} kept, {excluded_count} excluded from {total} total"
    )
    return kept
