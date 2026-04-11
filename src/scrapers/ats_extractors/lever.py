from __future__ import annotations

from typing import List

from bs4 import BeautifulSoup

from src.models.job import Job


def extract_lever(html: str, url: str, source_config: dict) -> List[Job]:
    soup = BeautifulSoup(html, "lxml")
    org = source_config.get("org_static") or source_config.get("name", "")
    category = source_config.get("category", "general")
    country = source_config.get("country", "uk")
    source_name = source_config.get("name", "")
    jobs: List[Job] = []

    for posting in soup.select(".postings-group .posting"):
        title_el = posting.select_one(".posting-title h5")
        if not title_el:
            title_el = posting.select_one(".posting-title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)

        link_el = posting.select_one("a")
        if not link_el:
            continue
        job_url = link_el.get("href", "")
        if not job_url or not job_url.startswith("http"):
            continue

        loc_el = posting.select_one(".posting-categories .location")
        location = loc_el.get_text(strip=True) if loc_el else None

        team_el = posting.select_one(".posting-categories .team")
        team = team_el.get_text(strip=True) if team_el else None

        desc = team or ""

        jobs.append(Job(
            title=title,
            url=job_url,
            organisation=org,
            description=desc,
            source_name=source_name,
            category=category,
            country=country,
            location=location,
        ))

    return jobs
