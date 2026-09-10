"""
Tests for the Civil Service Jobs dedicated scraper.

Fixtures used:
  csj_results_sort_opening.html  -- first results page with sort=opening (most-recent);
                                     captured 2026-09-10, no personal data.
  csj_esearch_response.html      -- results page returned by the initial esearch POST
                                     (sort=closing server default); used to verify
                                     _sort_refresh_url builds the correct GET URL.

No network access: the HTTP mocks test the sort-refresh flow end-to-end.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from src.scrapers.dedicated.civil_service_jobs import (
    CSJ_SORT,
    MAX_PAGES_PER_KEYWORD,
    SEARCH_KEYWORDS,
    Scraper,
    _canonical_csj_url,
)

FIXTURES = Path(__file__).parent / "fixtures"

SOURCE_CONFIG = {
    "name": "Civil Service Jobs",
    "url": "https://www.civilservicejobs.service.gov.uk/csr/jobs.cgi",
    "category": "government",
    "country": "uk",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _scraper() -> Scraper:
    return Scraper(SOURCE_CONFIG)


# ── _parse_jobs (fixture: sort=opening page) ──────────────────────────────────

def test_parse_jobs_yields_25_rows():
    soup = BeautifulSoup(_fixture("csj_results_sort_opening.html"), "lxml")
    jobs = _scraper()._parse_jobs(soup)
    assert len(jobs) == 25


def test_parse_jobs_closing_dates_not_monotonically_ascending():
    """sort=opening results have closing dates spread over weeks, not ascending."""
    soup = BeautifulSoup(_fixture("csj_results_sort_opening.html"), "lxml")
    jobs = _scraper()._parse_jobs(soup)
    closings = [j.closing_date for j in jobs if j.closing_date]
    assert closings, "No closing dates found"
    assert closings != sorted(closings), (
        "Closing dates are monotonically ascending, which would indicate "
        "sort=closing (server default) rather than sort=opening (most recent)"
    )


def test_parse_jobs_closing_dates_span_multiple_weeks():
    """sort=opening: at least 5 distinct closing dates in the first 25 rows."""
    soup = BeautifulSoup(_fixture("csj_results_sort_opening.html"), "lxml")
    jobs = _scraper()._parse_jobs(soup)
    unique_dates = {j.closing_date for j in jobs if j.closing_date}
    assert len(unique_dates) >= 5, (
        f"Only {len(unique_dates)} unique closing dates; expected >= 5 for a "
        "most-recent sort"
    )


def test_parse_jobs_canonical_url_stable():
    """Canonical URL strips session-bound SID params; does not contain 'reqsig'."""
    soup = BeautifulSoup(_fixture("csj_results_sort_opening.html"), "lxml")
    jobs = _scraper()._parse_jobs(soup)
    for job in jobs:
        assert "reqsig" not in job.url, f"Session param in canonical URL: {job.url}"
        assert "usersearchcontext" not in job.url


# ── _sort_refresh_url ─────────────────────────────────────────────────────────

def test_sort_refresh_url_found_on_esearch_response():
    """_sort_refresh_url returns a non-None URL from the esearch POST response."""
    soup = BeautifulSoup(_fixture("csj_esearch_response.html"), "lxml")
    url = _scraper()._sort_refresh_url(soup)
    assert url is not None, "_sort_refresh_url returned None; GET form not found"


def test_sort_refresh_url_contains_csj_sort():
    """The built URL includes sort=<CSJ_SORT> in the query string."""
    soup = BeautifulSoup(_fixture("csj_esearch_response.html"), "lxml")
    url = _scraper()._sort_refresh_url(soup) or ""
    assert f"sort={CSJ_SORT}" in url, (
        f"Expected sort={CSJ_SORT} in URL; got: {url[:200]}"
    )


def test_sort_refresh_url_contains_submit_token():
    """The built URL includes submit_results_sort_form (the Refresh sort button value)."""
    soup = BeautifulSoup(_fixture("csj_esearch_response.html"), "lxml")
    url = _scraper()._sort_refresh_url(soup) or ""
    assert "submit_results_sort_form" in url


def test_sort_refresh_url_targets_index_cgi():
    """The Refresh sort form targets index.cgi, not esearch.cgi."""
    soup = BeautifulSoup(_fixture("csj_esearch_response.html"), "lxml")
    url = _scraper()._sort_refresh_url(soup) or ""
    assert "index.cgi" in url, f"Expected index.cgi; got: {url[:120]}"


def test_sort_refresh_url_returns_none_when_form_absent():
    """Returns None gracefully when the sort form is not present."""
    soup = BeautifulSoup("<html><body><p>No form here</p></body></html>", "lxml")
    assert _scraper()._sort_refresh_url(soup) is None


# ── CSJ_SORT constant ─────────────────────────────────────────────────────────

def test_csj_sort_is_opening():
    assert CSJ_SORT == "opening"


# ── SEARCH_KEYWORDS ───────────────────────────────────────────────────────────

def test_mandatory_keywords_present():
    mandatory = {"policy", "analyst", "parliamentary", "diplomatic",
                 "graduate scheme", "fast stream"}
    assert mandatory.issubset(set(SEARCH_KEYWORDS)), (
        f"Missing mandatory keywords: {mandatory - set(SEARCH_KEYWORDS)}"
    )


def test_keyword_count_reduced():
    """Trimmed list must have fewer than the original 25 keywords."""
    assert len(SEARCH_KEYWORDS) < 25, (
        f"Expected fewer than 25 keywords; got {len(SEARCH_KEYWORDS)}"
    )


# ── Async scrape: sort-refresh flow (HTTP mocked) ─────────────────────────────

@pytest.mark.asyncio
async def test_scrape_issues_sort_refresh_get_after_esearch_post():
    """
    After the esearch POST, the scraper must issue a GET to index.cgi with
    sort=CSJ_SORT to apply the sort.  ALTCHA is mocked out; the test only
    checks the sort-refresh behaviour in _search_keyword.
    """
    scraper = _scraper()
    sorted_html = _fixture("csj_results_sort_opening.html")
    esearch_html = _fixture("csj_esearch_response.html")

    # Minimal home-page HTML: just enough for esearch form detection.
    home_html = """
    <html><body>
      <form action="https://www.civilservicejobs.service.gov.uk/csr/esearch.cgi">
        <input name="SID" value="dGVzdA=="/>
      </form>
    </body></html>
    """

    call_log: list[tuple[str, str]] = []

    def _resp(html: str) -> MagicMock:
        r = MagicMock()
        r.text = html
        r.raise_for_status = MagicMock()
        return r

    async def mock_get(url, **kwargs):
        url_s = str(url)
        call_log.append(("GET", url_s))
        if "index.cgi" in url_s:
            # This is the sort-refresh call: return the sorted-results fixture
            return _resp(sorted_html)
        # Home-page fetch per keyword
        return _resp(home_html)

    async def mock_post(url, **kwargs):
        call_log.append(("POST", str(url)))
        # esearch POST: return the real esearch response so _sort_refresh_url finds the form
        return _resp(esearch_html)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=mock_get)
    mock_client.post = AsyncMock(side_effect=mock_post)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("src.scrapers.dedicated.civil_service_jobs.httpx.AsyncClient",
               return_value=mock_client):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            # Patch _solve_altcha to a no-op: the ALTCHA flow is tested elsewhere
            with patch.object(scraper, "_solve_altcha", new=AsyncMock()):
                jobs = await scraper.scrape()

    # At least one GET to index.cgi was made (the sort-refresh step)
    get_index_calls = [u for m, u in call_log if m == "GET" and "index.cgi" in u]
    assert get_index_calls, (
        "No GET to index.cgi found in call log; sort-refresh step was not triggered.\n"
        f"All calls: {call_log}"
    )

    # sort=opening appears in at least one index.cgi GET URL
    assert any(f"sort={CSJ_SORT}" in u for u in get_index_calls), (
        f"sort={CSJ_SORT} not found in any index.cgi GET.\nCalls: {get_index_calls}"
    )

    # Jobs were returned (fixture has 25 per page; dedup collapses across keywords)
    assert len(jobs) > 0
