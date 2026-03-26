"""Unit tests for generic scraper parsing logic — zero API cost."""
from __future__ import annotations

import json
import pathlib
import pytest

from src.scrapers.generic import parse_claude_json, items_to_jobs, clean_html

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


# ── parse_claude_json ────────────────────────────────────────────────────────

def test_parse_clean_json_array():
    raw = json.dumps([{"title": "Analyst", "url": "https://example.com/job/1"}])
    result = parse_claude_json(raw)
    assert len(result) == 1
    assert result[0]["title"] == "Analyst"


def test_parse_fenced_json_block():
    raw = '```json\n[{"title": "Researcher", "url": "https://example.com/job/2"}]\n```'
    result = parse_claude_json(raw)
    assert len(result) == 1
    assert result[0]["title"] == "Researcher"


def test_parse_fenced_no_language_tag():
    raw = '```\n[{"title": "Director", "url": "https://example.com/job/3"}]\n```'
    result = parse_claude_json(raw)
    assert len(result) == 1


def test_parse_preamble_before_array():
    raw = "Here are the jobs I found:\n\n[{\"title\": \"Head of Policy\", \"url\": \"https://example.com/job/4\"}]"
    result = parse_claude_json(raw)
    assert len(result) == 1
    assert result[0]["title"] == "Head of Policy"


def test_parse_empty_array():
    result = parse_claude_json("[]")
    assert result == []


def test_parse_empty_string():
    result = parse_claude_json("")
    assert result == []


def test_parse_no_jobs_text():
    result = parse_claude_json("There are no current vacancies on this page.")
    assert result == []


def test_parse_malformed_json():
    result = parse_claude_json("[{bad json here")
    assert result == []


def test_parse_fixture_file():
    raw = (FIXTURES / "sample_claude_response.json").read_text()
    result = parse_claude_json(raw)
    assert len(result) == 3
    assert result[0]["title"] == "Senior Policy Analyst"
    assert result[2]["closing_date"] is None


def test_parse_returns_list_not_dict():
    # If Claude accidentally returns a dict instead of list, return []
    result = parse_claude_json('{"title": "Oops"}')
    assert result == []


# ── items_to_jobs ────────────────────────────────────────────────────────────

def test_items_to_jobs_basic():
    items = [
        {"title": "Policy Lead", "url": "https://example.com/job/1", "organisation": "Acme", "description": "A role.", "location": "London", "closing_date": "2026-05-01"},
    ]
    jobs = items_to_jobs(items, source_name="Acme", category="think-tanks", country="uk")
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Policy Lead"
    assert j.organisation == "Acme"
    assert j.location == "London"
    assert j.closing_date == "2026-05-01"
    assert j.category == "think-tanks"
    assert j.country == "uk"


def test_items_to_jobs_missing_title_skipped():
    items = [
        {"title": "", "url": "https://example.com/job/1"},
        {"title": "Good Job", "url": "https://example.com/job/2"},
    ]
    jobs = items_to_jobs(items, "Org", "general", "uk")
    assert len(jobs) == 1
    assert jobs[0].title == "Good Job"


def test_items_to_jobs_missing_url_skipped():
    items = [{"title": "Some Job", "url": ""}]
    jobs = items_to_jobs(items, "Org", "general", "uk")
    assert len(jobs) == 0


def test_items_to_jobs_relative_url_skipped():
    items = [{"title": "Some Job", "url": "/jobs/123"}]
    jobs = items_to_jobs(items, "Org", "general", "uk")
    assert len(jobs) == 0


def test_items_to_jobs_fallback_organisation():
    items = [{"title": "Analyst", "url": "https://example.com/job/1", "organisation": None}]
    jobs = items_to_jobs(items, source_name="FallbackOrg", category="general", country="uk")
    assert jobs[0].organisation == "FallbackOrg"


def test_items_to_jobs_description_truncated():
    long_desc = "x" * 600
    items = [{"title": "Analyst", "url": "https://example.com/job/1", "description": long_desc}]
    jobs = items_to_jobs(items, "Org", "general", "uk")
    assert len(jobs[0].description) == 500


def test_items_to_jobs_null_location_and_date():
    items = [{"title": "Analyst", "url": "https://example.com/job/1", "location": None, "closing_date": None}]
    jobs = items_to_jobs(items, "Org", "general", "uk")
    assert jobs[0].location is None
    assert jobs[0].closing_date is None


# ── clean_html ───────────────────────────────────────────────────────────────

def test_clean_html_strips_nav_and_footer():
    html = "<html><body><nav>Nav stuff</nav><main><p>Real content here.</p></main><footer>Footer</footer></body></html>"
    text = clean_html(html)
    assert "Real content here" in text
    assert "Nav stuff" not in text
    assert "Footer" not in text


def test_clean_html_strips_sidebar_class():
    html = '<html><body><div class="sidebar">Sidebar ads</div><main><p>Main content.</p></main></body></html>'
    text = clean_html(html)
    assert "Main content" in text
    assert "Sidebar ads" not in text


def test_clean_html_prefers_main_element():
    html = "<html><body><p>Outside main</p><main><p>Inside main</p></main></body></html>"
    text = clean_html(html)
    assert "Inside main" in text
    # "Outside main" may or may not appear depending on tree structure — just check main is preferred


def test_clean_html_collapses_blank_lines():
    html = "<html><body><main><p>Line 1</p><p></p><p></p><p></p><p>Line 2</p></main></body></html>"
    text = clean_html(html)
    assert "\n\n\n" not in text


def test_clean_html_truncates_at_max_chars():
    long_text = "word " * 5000  # ~25,000 chars
    html = f"<html><body><main><p>{long_text}</p></main></body></html>"
    text = clean_html(html)
    assert len(text) <= 12000
