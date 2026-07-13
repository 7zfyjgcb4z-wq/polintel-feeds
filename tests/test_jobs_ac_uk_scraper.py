"""
Tests for jobs.ac.uk dedicated scraper.

Covers: HTML parsing, multi-facet configuration, and cross-facet URL deduplication.
No network access: HTTP is mocked for the async scrape() tests.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bs4 import BeautifulSoup

from src.scrapers.dedicated.jobs_ac_uk import Scraper, DISCIPLINE_FACETS

SOURCE_CONFIG = {
    "name": "jobs.ac.uk",
    "url": "https://www.jobs.ac.uk/search/politics-and-government",
    "category": "general",
    "country": "uk",
}

# Minimal fixture: one job card matching the live jobs.ac.uk DOM structure
ONE_JOB_HTML = """
<html><body>
  <div class="j-search-result__result">
    <div class="j-search-result__text">
      <a href="/jobs/12345/lecturer-in-ir.html">Lecturer in International Relations</a>
      <div>Location: London</div>
    </div>
    <div class="j-search-result__employer"><b>University of Somewhere</b></div>
    <div class="j-search-result__info">£45,000 - £55,000</div>
    <span class="j-search-result__date--blue">30 Sep 2026</span>
  </div>
</body></html>
"""

EMPTY_HTML = "<html><body></body></html>"


# ── Parsing tests (synchronous, no HTTP) ─────────────────────────────────────

def test_parse_jobs_extracts_title_and_url():
    scraper = Scraper(SOURCE_CONFIG)
    soup = BeautifulSoup(ONE_JOB_HTML, "lxml")
    jobs = scraper._parse_jobs(soup)
    assert len(jobs) == 1
    assert jobs[0].title == "Lecturer in International Relations"
    assert jobs[0].url == "https://www.jobs.ac.uk/jobs/12345/lecturer-in-ir.html"


def test_parse_jobs_extracts_organisation():
    scraper = Scraper(SOURCE_CONFIG)
    soup = BeautifulSoup(ONE_JOB_HTML, "lxml")
    jobs = scraper._parse_jobs(soup)
    assert jobs[0].organisation == "University of Somewhere"


def test_parse_jobs_extracts_location():
    scraper = Scraper(SOURCE_CONFIG)
    soup = BeautifulSoup(ONE_JOB_HTML, "lxml")
    jobs = scraper._parse_jobs(soup)
    assert jobs[0].location == "London"


def test_parse_jobs_extracts_closing_date():
    scraper = Scraper(SOURCE_CONFIG)
    soup = BeautifulSoup(ONE_JOB_HTML, "lxml")
    jobs = scraper._parse_jobs(soup)
    assert jobs[0].closing_date == "2026-09-30"


def test_parse_jobs_empty_page_returns_empty_list():
    scraper = Scraper(SOURCE_CONFIG)
    soup = BeautifulSoup(EMPTY_HTML, "lxml")
    assert scraper._parse_jobs(soup) == []


# ── Facet configuration tests ─────────────────────────────────────────────────

def test_multiple_discipline_facets_configured():
    assert len(DISCIPLINE_FACETS) > 1


def test_politics_and_government_facet_present():
    assert "politics-and-government" in DISCIPLINE_FACETS


def test_environmental_sciences_facet_present():
    assert "environmental-sciences" in DISCIPLINE_FACETS


# ── Multi-facet + dedup test (async, HTTP mocked) ─────────────────────────────

@pytest.mark.asyncio
async def test_cross_facet_dedup_collapses_duplicate_urls():
    """A job URL returned by both facets appears only once in the final list."""
    scraper = Scraper(SOURCE_CONFIG)

    job_response = MagicMock()
    job_response.text = ONE_JOB_HTML
    job_response.raise_for_status = MagicMock()

    # Each facet returns one job page (1 job < 25 → stops), so total calls = len(DISCIPLINE_FACETS)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=job_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("src.scrapers.dedicated.jobs_ac_uk.httpx.AsyncClient", return_value=mock_client):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            jobs = await scraper.scrape()

    # Same URL served for every facet; dedup must collapse to exactly one job
    assert len(jobs) == 1
    assert jobs[0].url == "https://www.jobs.ac.uk/jobs/12345/lecturer-in-ir.html"
    # One HTTP request was made per facet
    assert mock_client.get.call_count == len(DISCIPLINE_FACETS)


@pytest.mark.asyncio
async def test_scrape_requests_each_facet():
    """The scraper issues at least one request per configured discipline facet."""
    scraper = Scraper(SOURCE_CONFIG)

    job_response = MagicMock()
    job_response.text = ONE_JOB_HTML
    job_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=job_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("src.scrapers.dedicated.jobs_ac_uk.httpx.AsyncClient", return_value=mock_client):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await scraper.scrape()

    called_urls = [str(call.args[0]) for call in mock_client.get.call_args_list]
    for facet in DISCIPLINE_FACETS:
        assert any(facet in u for u in called_urls), f"No request made for facet '{facet}'"
