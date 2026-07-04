"""Golden-file test for the LobbyingJobs.com list-page rewrite.

tests/fixtures/lobbyingjobs_list.html was fetched once, live, on 2026-07-04
(https://lobbyingjobs.com/jobs, UA "Pol-Intel/1.0 (contact@orison.co)", 200 OK)
after the site's Tailwind rebuild broke the prior `article.listing-item__jobs`
selectors. No network access happens in this test.
"""
from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from src.scrapers.dedicated.lobbyingjobs import Scraper

FIXTURES = Path(__file__).parent / "fixtures"

SOURCE_CONFIG = {
    "name": "LobbyingJobs.com",
    "url": "https://lobbyingjobs.com",
    "category": "us-government-affairs",
    "country": "us",
    "partisan_lean": "unknown",
}


def _parse_fixture():
    scraper = Scraper(SOURCE_CONFIG)
    html = (FIXTURES / "lobbyingjobs_list.html").read_text()
    soup = BeautifulSoup(html, "lxml")
    return scraper._parse_page(soup, seen_urls=set(), partisan_lean="unknown")


def test_fixture_parses_expected_job_count():
    jobs = _parse_fixture()
    assert len(jobs) == 20


def test_all_jobs_have_title_and_url():
    jobs = _parse_fixture()
    for job in jobs:
        assert job.title.strip()
        assert job.url.startswith("https://lobbyingjobs.com/job/")


def test_known_job_present():
    jobs = _parse_fixture()
    titles = [j.title for j in jobs]
    assert "Associate, Federal Affairs" in titles


def test_organisation_and_location_extracted():
    jobs = _parse_fixture()
    by_title = {j.title: j for j in jobs}
    job = by_title["Associate, Federal Affairs"]
    assert job.organisation == "DoorDash"
    assert job.location == "Washington, DC"


def test_zero_cards_logs_warning(caplog):
    scraper = Scraper(SOURCE_CONFIG)
    soup = BeautifulSoup("<html><body>no jobs here</body></html>", "lxml")
    import logging
    with caplog.at_level(logging.WARNING):
        jobs = scraper._parse_page(soup, seen_urls=set(), partisan_lean="unknown")
    assert jobs == []
    assert any("matched 0 elements" in rec.message for rec in caplog.records)
