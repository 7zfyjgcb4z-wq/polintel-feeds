from __future__ import annotations

from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.models.job import Job


def extract_applied(html: str, url: str, source_config: dict) -> List[Job]:
    soup = BeautifulSoup(html, "lxml")
    org = source_config.get("org_static") or source_config.get("name", "")
    category = source_config.get("category", "general")
    country = source_config.get("country", "uk")
    source_name = source_config.get("name", "")
    jobs: List[Job] = []

    # Applied renders jobs as cards; try common selector patterns
    job_cards = (
        soup.select(".job-card")
        or soup.select(".vacancy-card")
        or soup.select("[data-testid='job-listing']")
        or soup.select("article.job")
    )

    for card in job_cards:
        link_el = card.find("a", href=True)
        if not link_el:
            continue
        title = link_el.get_text(strip=True)
        href = link_el["href"]
        job_url = href if href.startswith("http") else urljoin(url, href)

        if not title or not job_url:
            continue

        loc_el = card.select_one(".location") or card.select_one("[data-location]")
        location = loc_el.get_text(strip=True) if loc_el else None

        close_el = card.select_one(".closing-date") or card.select_one("[data-closing]")
        closing_date = close_el.get_text(strip=True) if close_el else None

        jobs.append(Job(
            title=title,
            url=job_url,
            organisation=org,
            description="",
            source_name=source_name,
            category=category,
            country=country,
            location=location,
            closing_date=closing_date,
        ))

    return jobs
