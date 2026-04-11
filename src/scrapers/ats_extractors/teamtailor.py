from __future__ import annotations

from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.models.job import Job


def extract_teamtailor(html: str, url: str, source_config: dict) -> List[Job]:
    soup = BeautifulSoup(html, "lxml")
    org = source_config.get("org_static") or source_config.get("name", "")
    category = source_config.get("category", "general")
    country = source_config.get("country", "uk")
    source_name = source_config.get("name", "")
    jobs: List[Job] = []

    # TeamTailor renders jobs in a list; try several selector patterns
    job_items = (
        soup.select("#tt-careers li")
        or soup.select(".jobs-list li")
        or soup.select("[data-hook='job-list'] li")
        or soup.select("ul.positions li")
    )

    for item in job_items:
        link_el = item.find("a", href=True)
        if not link_el:
            continue
        title = link_el.get_text(strip=True)
        href = link_el["href"]
        job_url = href if href.startswith("http") else urljoin(url, href)

        loc_el = item.select_one(".location") or item.select_one("[data-hook='job-location']")
        location = loc_el.get_text(strip=True) if loc_el else None

        if not title or not job_url:
            continue

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
