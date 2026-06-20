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


# ── New platforms (internship/graduate pipeline extension) ───────────────────

def test_detect_workable_by_link():
    html = '<html><body><a href="https://apply.workable.com/chatham-house/">Apply</a></body></html>'
    assert detect_ats(html, "https://chathamhouse.org") == "workable"


def test_detect_workable_by_embed_hook():
    html = '<html><body><div id="whr_embed_hook"></div><script src="https://www.workable.com/assets/embed.js"></script></body></html>'
    assert detect_ats(html, "https://example.com/careers") == "workable"


def test_detect_workable_by_js_variable():
    html = '<html><body><script>var whr_workable = {account_id: "abc"};</script></body></html>'
    assert detect_ats(html, "https://example.com/careers") == "workable"


def test_detect_icims_by_link():
    html = '<html><body><a href="https://careers-brookings.icims.com/jobs/search">Jobs</a></body></html>'
    assert detect_ats(html, "https://brookings.edu/careers") == "icims"


def test_detect_icims_by_iframe():
    html = '<html><body><iframe src="https://careers-cfr.icims.com/jobs/search?in_iframe=1"></iframe></body></html>'
    assert detect_ats(html, "https://cfr.org/careers") == "icims"


def test_detect_icims_by_class():
    html = '<html><body><ul class="iCIMS_JobList"><li class="iCIMS_JobCardItem"></li></ul></body></html>'
    assert detect_ats(html, "https://example.com/careers") == "icims"


def test_detect_cornerstone_by_link():
    html = '<html><body><a href="https://worldbank.csod.com/ux/ats/careersite/1/home">Careers</a></body></html>'
    assert detect_ats(html, "https://worldbank.org/careers") == "cornerstone"


def test_detect_cornerstone_by_iframe():
    html = '<html><body><iframe src="https://acme.csod.com/ux/ats/careersite/2/home"></iframe></body></html>'
    assert detect_ats(html, "https://acme.org/careers") == "cornerstone"


def test_detect_applicantpro_by_link():
    html = '<html><body><a href="https://carnegieendowment.applicantpro.com/jobs/">Apply</a></body></html>'
    assert detect_ats(html, "https://carnegieendowment.org/careers") == "applicantpro"


def test_detect_applicantpro_in_html():
    html = '<html><body><script src="https://cdn.applicantpro.com/embed.js"></script></body></html>'
    assert detect_ats(html, "https://example.com/careers") == "applicantpro"


def test_detect_applicantstack_by_link():
    html = '<html><body><a href="https://heritage.applicantstack.com/x/openings">Open positions</a></body></html>'
    assert detect_ats(html, "https://heritage.org/careers") == "applicantstack"


def test_detect_applicantstack_in_html():
    html = '<html><body><script>var atsEmbed = {provider: "applicantstack.com"};</script></body></html>'
    assert detect_ats(html, "https://example.com/careers") == "applicantstack"


def test_detect_oracle_hcm_by_ui_url():
    html = '<html><body><a href="https://eoff.fa.em1.ukg.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1">Jobs</a></body></html>'
    assert detect_ats(html, "https://bankofengland.co.uk/careers") == "oracle_hcm"


def test_detect_oracle_hcm_by_iframe():
    html = '<html><body><iframe src="https://eoff.fa.em1.ukg.oraclecloud.com/hcmUI/..."></iframe></body></html>'
    assert detect_ats(html, "https://bankofengland.co.uk/careers") == "oracle_hcm"


def test_detect_oracle_hcm_by_inline_string():
    html = '<html><body><script>var config = {url: "https://ipsos.fa.eu.oraclecloud.com/hcmUI/CandidateExperience"};</script></body></html>'
    assert detect_ats(html, "https://ipsos.com/careers") == "oracle_hcm"
