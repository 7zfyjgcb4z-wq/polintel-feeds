from __future__ import annotations

from src.scrapers.ats_detector import detect_ats


def test_detect_greenhouse_by_div_class():
    html = '<html><body><div class="opening"><a href="/jobs/1">Policy Analyst</a></div></body></html>'
    assert detect_ats(html, "https://example.com/careers") == "greenhouse"


def test_detect_greenhouse_by_id():
    html = '<html><body><div id="grnhse_app">Greenhouse embed</div></body></html>'
    assert detect_ats(html, "https://example.com/careers") == "greenhouse"


def test_detect_greenhouse_by_link():
    html = '<html><body><a href="https://boards.greenhouse.io/acme/jobs/1">Apply</a></body></html>'
    assert detect_ats(html, "https://example.com/careers") == "greenhouse"


def test_detect_greenhouse_by_iframe():
    html = '<html><body><iframe src="https://boards.greenhouse.io/embed/job_board?for=acme"></iframe></body></html>'
    assert detect_ats(html, "https://example.com/careers") == "greenhouse"


def test_detect_lever_by_link():
    html = '<html><body><a href="https://jobs.lever.co/acme/abc123">Senior Adviser</a></body></html>'
    assert detect_ats(html, "https://example.com/careers") == "lever"


def test_detect_lever_by_postings_group():
    html = '<html><body><div class="postings-group"><div class="posting">Job</div></div></body></html>'
    assert detect_ats(html, "https://example.com/careers") == "lever"


def test_detect_teamtailor_by_link():
    html = '<html><body><a href="https://career.teamtailor.com/acme">Jobs</a></body></html>'
    assert detect_ats(html, "https://example.com/careers") == "teamtailor"


def test_detect_teamtailor_by_id():
    html = '<html><body><div id="tt-careers"><ul><li>Job 1</li></ul></div></body></html>'
    assert detect_ats(html, "https://example.com/careers") == "teamtailor"


def test_detect_workday():
    html = '<html><body><a href="https://acme.myworkdayjobs.com/careers">Jobs</a></body></html>'
    assert detect_ats(html, "https://example.com/careers") == "workday"


def test_detect_applied():
    html = '<html><body><a href="https://app.beapplied.com/apply/abc123">Apply</a></body></html>'
    assert detect_ats(html, "https://example.com/careers") == "applied"


def test_detect_ashby():
    html = '<html><body><a href="https://jobs.ashbyhq.com/acme/policy-lead">Policy Lead</a></body></html>'
    assert detect_ats(html, "https://example.com/careers") == "ashby"


def test_detect_none():
    html = '<html><body><ul><li><a href="/jobs/1">Policy Analyst</a></li></ul></body></html>'
    assert detect_ats(html, "https://example.com/careers") is None


def test_detect_does_not_raise_on_empty_html():
    assert detect_ats("", "https://example.com") is None
