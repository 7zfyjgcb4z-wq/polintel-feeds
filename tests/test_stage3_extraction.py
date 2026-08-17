"""Golden-file tests for the Stage 3 shared extraction mechanisms.

Fixtures were fetched once, politely (repo UA, 1.5s apart), on 2026-07-03 and
saved under tests/fixtures/. No network access happens in these tests.

Fixture swaps from the spec's default URLs:
  - greenparty_job.html: the spec's default URL
    (.../work-for-us/campaign-organiser-north-lancashire/) no longer serves a
    job; captured instead from the first div.job-card link on the list page
    (https://greenparty.org.uk/get-involved/work-for-us/supporter-care-manager/).
  - pac_job.html, eurobrussels_expired.html, eurobrussels_live.html,
    paylocity_jswall.html: fetched from the spec's default URLs unchanged.
    eurobrussels_live.html captures
    /job_display/292473/Policy_Strategist_Economist_ESM_European_Stability_Mechanism_Luxembourg_Luxembourg.
  - w4mp_job.html (E4): fetched 2026-07-04 from the first item link in
    https://www.w4mpjobs.org/RSS.aspx
    (JobDetails.aspx?jobid=99637, "Campaign Manager").
  - myjobscotland_job.html: synthetic minimal page confirming that
    _parse_job_ld traverses @graph to find a nested JobPosting.
    The live pattern was confirmed against admin.myjobscotland.gov.uk 2026-08-17.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.enrichment.readability_enricher import _parse_job_ld, enrich_jobs
from src.models.job import Job

FIXTURES = Path(__file__).parent / "fixtures"

PAC_CFG = {
    "content_scope": "article.pa_jobs",
    "labelled_fields": {
        "organisation": "Organization",
        "location": "Location",
        "posted_date": "Date Posted",
        "posted_date_format": "%m/%d/%Y",
    },
}
GREEN_PARTY_CFG = {
    "content_scope": "div.entry-content",
    "labelled_fields": {
        "closing_date": "Closing Date",
        "closing_date_format": "%d %b %Y",
    },
}
EUROBRUSSELS_CFG = {"org_from_page": True}
W4MP_CFG = {
    "labelled_fields": {
        "organisation": "Working For",
        "location": "Location",
        "posted_date": "Date Added",
        "posted_date_format": "%d %B %Y",
        "closing_date": "Closing Date",
        "closing_date_format": "%d %B %Y",
    },
    "body_between": {
        "start": "Job Details",
        "end": "Go back to search results",
    },
}


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


async def _enrich_one_job(job: Job, source_cfg: dict, fixture: str) -> Job:
    with patch(
        "src.enrichment.readability_enricher._fetch_html",
        AsyncMock(return_value=_load(fixture)),
    ):
        await enrich_jobs([job], source_configs={job.source_name: source_cfg}, delay=0)
    return job


@pytest.mark.asyncio
async def test_pac_labelled_fields_and_consent_strip():
    job = Job(
        title="Manager, Government Relations",
        url="https://pac.org/job/manager-government-relations-21",
        organisation="Public Affairs Council Jobs",
        description="",
        source_name="Public Affairs Council Jobs",
        category="us-government-affairs",
        country="us",
    )
    await _enrich_one_job(job, PAC_CFG, "pac_job.html")

    assert "To provide the best experiences" not in job.description
    assert "International Dairy Foods Association" in job.description
    assert job.organisation == "International Dairy Foods Association (IDFA)"
    assert job.location == "Washington, DC"
    assert job.posted_date == "2026-04-23"
    assert job.description_source == "structured"


@pytest.mark.asyncio
async def test_green_party_consent_strip_and_closing_date():
    job = Job(
        title="Supporter Care Manager",
        url="https://greenparty.org.uk/get-involved/work-for-us/supporter-care-manager/",
        organisation="Green Party of England and Wales",
        description="",
        source_name="Green Party",
        category="political-parties",
        country="uk",
    )
    await _enrich_one_job(job, GREEN_PARTY_CFG, "greenparty_job.html")

    assert "To provide the best experiences" not in job.description
    assert "About This Role" in job.description
    assert job.closing_date == "2026-06-18"


@pytest.mark.asyncio
async def test_eurobrussels_expired_page_is_dropped():
    job = Job(
        title="Senior Policy Adviser",
        url="https://www.eurobrussels.com/job_display/289254/Senior_Policy_Adviser_EUROPEX_Association_of_European_Energy_Exchanges_Brussels_Belgium",
        organisation="EuroBrussels",
        description="",
        source_name="EuroBrussels",
        category="eu-affairs",
        country="brussels",
    )
    await _enrich_one_job(job, EUROBRUSSELS_CFG, "eurobrussels_expired.html")

    assert job._dead_page is True
    # Pipeline drop filter (src/pipeline.py) applied directly here.
    survivors = [j for j in [job] if not getattr(j, "_dead_page", False)]
    assert survivors == []


@pytest.mark.asyncio
async def test_eurobrussels_live_page_org_location_deadline():
    job = Job(
        title="Policy Strategist/Economist",
        url="https://www.eurobrussels.com/job_display/292473/Policy_Strategist_Economist_ESM_European_Stability_Mechanism_Luxembourg_Luxembourg",
        organisation="EuroBrussels",
        description="",
        source_name="EuroBrussels",
        category="eu-affairs",
        country="brussels",
    )
    await _enrich_one_job(job, EUROBRUSSELS_CFG, "eurobrussels_live.html")

    assert job.organisation == "ESM - European Stability Mechanism"
    assert "_" not in job.organisation
    assert job.location
    assert job.closing_date is not None
    assert re_matches_iso_date(job.closing_date)


@pytest.mark.asyncio
async def test_paylocity_js_wall_body_refused():
    job = Job(
        title="Some Job",
        url="https://recruiting.paylocity.com/recruiting/jobs/All/43d988e3-6446-4a25-8e28-28602ea60858/careers",
        organisation="Some Employer",
        description="",
        source_name="Some Paylocity Source",
        category="us-government-affairs",
        country="us",
    )
    await _enrich_one_job(job, {}, "paylocity_jswall.html")

    assert job.description == ""
    assert job.description_source == "none"
    assert getattr(job, "_dead_page", False) is False


@pytest.mark.asyncio
async def test_fail_loud_never_returns_page_chrome_as_body():
    job = Job(
        title="Some Job",
        url="https://recruiting.paylocity.com/recruiting/jobs/All/43d988e3-6446-4a25-8e28-28602ea60858/careers",
        organisation="Some Employer",
        description="",
        source_name="Some Paylocity Source",
        category="us-government-affairs",
        country="us",
    )
    await _enrich_one_job(job, {}, "paylocity_jswall.html")

    assert "enable javascript" not in job.description.lower()
    assert job.description == ""


@pytest.mark.asyncio
async def test_w4mp_body_between_and_labelled_fields():
    job = Job(
        title="Campaign Manager",
        url="http://www.w4mpjobs.org/JobDetails.aspx?jobid=99637",
        organisation="W4MP",
        description="",
        source_name="W4MP",
        category="general",
        country="uk",
    )
    await _enrich_one_job(job, W4MP_CFG, "w4mp_job.html")

    assert len(job.description) > 1000
    assert "Go back to search results" not in job.description
    assert "Subscribe to our RSS feed" not in job.description
    assert job.organisation == "Matt Vickers MP (Stockton West)"
    assert job.posted_date == "2026-07-02"
    assert re_matches_iso_date(job.posted_date)
    assert job.closing_date == "2026-07-23"
    assert re_matches_iso_date(job.closing_date)
    assert job.description_source == "structured"


@pytest.mark.asyncio
async def test_w4mp_body_between_fail_loud_when_start_label_absent():
    job = Job(
        title="Campaign Manager",
        url="http://www.w4mpjobs.org/JobDetails.aspx?jobid=99637",
        organisation="W4MP",
        description="Existing RSS summary text that is short.",
        source_name="W4MP",
        category="general",
        country="uk",
    )
    cfg = dict(W4MP_CFG, body_between={"start": "Nonexistent Marker", "end": "Go back to search results"})
    await _enrich_one_job(job, cfg, "w4mp_job.html")

    assert job.description == "Existing RSS summary text that is short."


def re_matches_iso_date(value: str) -> bool:
    import re

    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))


# ── @graph traversal fix (fix/degraded-extractors) ───────────────────────────

def test_parse_job_ld_at_graph_extracts_nested_jobposting():
    """_parse_job_ld must traverse an @graph array and find a JobPosting node.

    myjobscotland (and sites using Yoast SEO / Rank Math) emit JSON-LD where
    @type is NOT at the document root — instead a @graph list holds a WebPage
    and a JobPosting side by side.  The pre-fix implementation tested only the
    top-level @type and returned empty metadata for ~one third of measured
    JSON-LD coverage.  This test uses the myjobscotland fixture (synthetic
    minimal page matching the live structure confirmed 2026-08-17).
    """
    html = _load("myjobscotland_job.html")
    meta = _parse_job_ld(html)

    assert meta["organisation"] == "West Dunbartonshire Council"
    assert meta["location"] == "Dumbarton"
    assert meta["closing_date"] == "2026-08-30"


def test_parse_job_ld_top_level_jobposting_still_works():
    """@graph traversal must not break the existing top-level @type path."""
    html = """<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting",
 "hiringOrganization":{"@type":"Organization","name":"Acme Ltd"},
 "jobLocation":{"@type":"Place","address":{"@type":"PostalAddress",
   "addressLocality":"London","addressRegion":"England"}},
 "validThrough":"2026-09-01T00:00:00"}
</script></head><body></body></html>"""
    meta = _parse_job_ld(html)

    assert meta["organisation"] == "Acme Ltd"
    assert meta["location"] == "London, England"
    assert meta["closing_date"] == "2026-09-01"


def test_parse_job_ld_at_graph_without_jobposting_returns_empty():
    """@graph that contains no JobPosting node must return the empty dict."""
    html = """<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"WebPage","@id":"https://example.com/page"},
  {"@type":"BreadcrumbList","itemListElement":[]}
]}
</script></head><body></body></html>"""
    meta = _parse_job_ld(html)

    assert meta == {"organisation": None, "location": None, "closing_date": None}


# ── EuroBrussels content_scope fix (fix/degraded-extractors) ─────────────────

@pytest.mark.asyncio
async def test_eurobrussels_content_scope_extracts_job_body():
    """With content_scope: div.jobDisplay the enricher must extract the real
    job body rather than sidebar widget text.

    The live fixture eurobrussels_live.html contains multiple .widget sidebar
    blocks and a hidden .modal-body.widget ("What do you think of this job?").
    On short job descriptions readability would score those widget divs above
    the body.  content_scope pins the extractor to div.jobDisplay, which
    contains the verified job content.
    """
    job = Job(
        title="Policy Strategist/Economist",
        url="https://www.eurobrussels.com/job_display/292473/Policy_Strategist_Economist_ESM_European_Stability_Mechanism_Luxembourg_Luxembourg",
        organisation="EuroBrussels",
        description="",
        source_name="EuroBrussels",
        category="eu-affairs",
        country="brussels",
    )
    cfg = {**EUROBRUSSELS_CFG, "content_scope": "div.jobDisplay"}
    await _enrich_one_job(job, cfg, "eurobrussels_live.html")

    # The job description body must contain role-specific content, not the widget
    assert len(job.description) > 500
    assert "What do you think of this job?" not in job.description
    assert "Top Jobs" not in job.description
    # Confirm actual job content is present
    assert "European Stability Mechanism" in job.description


# ── Freshness gate (fix/degraded-extractors) ─────────────────────────────────

@pytest.mark.asyncio
async def test_enrich_jobs_known_url_skips_detail_fetch():
    """Enricher must NOT fetch the detail page for a job whose URL is in
    known_urls (freshness gate added 2026-08-17 for PI EU TT sources).
    """
    job = Job(
        title="Policy Analyst",
        url="https://www.epc.eu/vacancies/policy-analyst",
        organisation="European Policy Centre (EPC)",
        description="",
        source_name="European Policy Centre",
        category="think-tanks",
        country="brussels",
    )
    fetch_calls: list[str] = []

    async def fake_fetch(url: str):
        fetch_calls.append(url)
        return "<html><body>Some error page</body></html>"

    with patch("src.enrichment.readability_enricher._fetch_html", AsyncMock(side_effect=fake_fetch)):
        await enrich_jobs(
            [job],
            known_urls={job.url},
            delay=0,
        )

    assert fetch_calls == [], "detail page must not be fetched for a known URL"
    assert job.description == ""  # description unchanged


@pytest.mark.asyncio
async def test_enrich_jobs_dead_page_signatures_drop_job():
    """A 200 OK response whose body contains a closed-job phrase must mark the
    job as dead (so the pipeline drops it) rather than storing the error text.
    """
    job = Job(
        title="Policy Analyst",
        url="https://www.epc.eu/vacancies/policy-analyst-old",
        organisation="European Policy Centre (EPC)",
        description="",
        source_name="European Policy Centre",
        category="think-tanks",
        country="brussels",
    )

    closed_page = (
        "<html><body>"
        "<h1>Vacancy details</h1>"
        "<p>This job is no longer available. The position has been filled.</p>"
        "</body></html>"
    )

    with patch("src.enrichment.readability_enricher._fetch_html", AsyncMock(return_value=closed_page)):
        await enrich_jobs([job], delay=0)

    assert getattr(job, "_dead_page", False) is True
