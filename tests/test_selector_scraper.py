from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.scrapers.selector_scraper import SelectorScraper

SAMPLE_HTML = """
<html><body>
  <ul>
    <li class="job-listing">
      <div class="job-title"><a href="/jobs/1">Policy Analyst</a></div>
      <div class="job-company">IPPR</div>
      <div class="job-location">London</div>
      <div class="job-deadline">2026-06-30</div>
    </li>
    <li class="job-listing">
      <div class="job-title"><a href="/jobs/2">Research Fellow</a></div>
      <div class="job-company">Chatham House</div>
      <div class="job-location">Remote</div>
      <div class="job-deadline">2026-07-15</div>
    </li>
    <li class="job-listing">
      <div class="job-title"><a href="https://abs.example.com/jobs/3">Head of Policy</a></div>
      <div class="job-company">ODI</div>
      <div class="job-location">Edinburgh</div>
    </li>
  </ul>
</body></html>
"""

SELECTORS = {
    "job_card": ".job-listing",
    "title": ".job-title a",
    "link": ".job-title a[href]",
    "organisation": ".job-company",
    "location": ".job-location",
    "closing_date": ".job-deadline",
}

SOURCE_CONFIG = {
    "name": "Test Source",
    "url": "https://example.com/jobs",
    "category": "think-tanks",
    "country": "uk",
}


def test_parse_extracts_all_jobs():
    scraper = SelectorScraper()
    jobs = scraper._parse(SAMPLE_HTML, "https://example.com/jobs", SELECTORS, SOURCE_CONFIG)
    assert len(jobs) == 3


def test_parse_extracts_title():
    scraper = SelectorScraper()
    jobs = scraper._parse(SAMPLE_HTML, "https://example.com/jobs", SELECTORS, SOURCE_CONFIG)
    assert jobs[0].title == "Policy Analyst"
    assert jobs[1].title == "Research Fellow"
    assert jobs[2].title == "Head of Policy"


def test_parse_resolves_relative_url():
    scraper = SelectorScraper()
    jobs = scraper._parse(SAMPLE_HTML, "https://example.com/jobs", SELECTORS, SOURCE_CONFIG)
    assert jobs[0].url == "https://example.com/jobs/1"


def test_parse_keeps_absolute_url():
    scraper = SelectorScraper()
    jobs = scraper._parse(SAMPLE_HTML, "https://example.com/jobs", SELECTORS, SOURCE_CONFIG)
    assert jobs[2].url == "https://abs.example.com/jobs/3"


def test_parse_extracts_organisation():
    scraper = SelectorScraper()
    jobs = scraper._parse(SAMPLE_HTML, "https://example.com/jobs", SELECTORS, SOURCE_CONFIG)
    assert jobs[0].organisation == "IPPR"
    assert jobs[1].organisation == "Chatham House"


def test_parse_extracts_location():
    scraper = SelectorScraper()
    jobs = scraper._parse(SAMPLE_HTML, "https://example.com/jobs", SELECTORS, SOURCE_CONFIG)
    assert jobs[0].location == "London"
    assert jobs[1].location == "Remote"


def test_parse_extracts_closing_date():
    scraper = SelectorScraper()
    jobs = scraper._parse(SAMPLE_HTML, "https://example.com/jobs", SELECTORS, SOURCE_CONFIG)
    assert jobs[0].closing_date == "2026-06-30"
    assert jobs[2].closing_date is None


def test_parse_uses_org_static_fallback():
    config_with_static = {**SOURCE_CONFIG, "org_static": "Static Org"}
    selectors_no_org = {k: v for k, v in SELECTORS.items() if k != "organisation"}
    scraper = SelectorScraper()
    jobs = scraper._parse(SAMPLE_HTML, "https://example.com/jobs", selectors_no_org, config_with_static)
    assert all(j.organisation == "Static Org" for j in jobs)


def test_parse_skips_cards_without_title():
    html = '<html><body><li class="job-listing"><div class="job-title"></div></li></body></html>'
    scraper = SelectorScraper()
    jobs = scraper._parse(html, "https://example.com", SELECTORS, SOURCE_CONFIG)
    assert len(jobs) == 0


def test_parse_returns_empty_on_no_card_selector():
    scraper = SelectorScraper()
    jobs = scraper._parse(SAMPLE_HTML, "https://example.com", {}, SOURCE_CONFIG)
    assert jobs == []


def test_sets_correct_category_and_country():
    scraper = SelectorScraper()
    jobs = scraper._parse(SAMPLE_HTML, "https://example.com/jobs", SELECTORS, SOURCE_CONFIG)
    assert jobs[0].category == "think-tanks"
    assert jobs[0].country == "uk"


@pytest.mark.asyncio
async def test_scrape_skips_requires_js():
    scraper = SelectorScraper()
    config = {**SOURCE_CONFIG, "requires_js": True}
    jobs = await scraper.scrape("https://example.com", SELECTORS, config)
    assert jobs == []
