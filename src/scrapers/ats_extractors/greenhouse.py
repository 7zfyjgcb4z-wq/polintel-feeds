from __future__ import annotations

from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.models.job import Job

GREENHOUSE_BASE = "https://boards.greenhouse.io"


def extract_greenhouse(html: str, url: str, source_config: dict) -> List[Job]:
    soup = BeautifulSoup(html, "lxml")
    org = source_config.get("org_static") or source_config.get("name", "")
    category = source_config.get("category", "general")
    country = source_config.get("country", "uk")
    source_name = source_config.get("name", "")
    jobs: List[Job] = []

    for opening in soup.select("div.opening"):
        link_el = opening.select_one("a")
        if not link_el:
            continue
        title = link_el.get_text(strip=True)
        href = link_el.get("href", "")
        if not href:
            continue
        if href.startswith("http"):
            job_url = href
        else:
            job_url = urljoin(GREENHOUSE_BASE, href)

        loc_el = opening.select_one(".location")
        location = loc_el.get_text(strip=True) if loc_el else None

        jobs.append(Job(
            title=title,
            url=job_url,
            organisation=org,
            description="",
            source_name=source_name,
            category=category,
            country=country,
            location=location,
        ))

    return jobs
